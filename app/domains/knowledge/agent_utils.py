import json
import re
from typing import Optional
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, MessagesState, END
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse
import chromadb

from app.core.config import settings
from app.core.graph.state import SharedState
from app.utils.time_utils import now_kst
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# --- 클라이언트 초기화 ---
# 모듈 로드 시 한 번만 연결. 요청마다 새로 연결하지 않음.
mongo_db = AsyncIOMotorClient(settings.MONGODB_URL)["meeting_assistant"]
chroma_client = chromadb.HttpClient(
    host=settings.CHROMA_HOST,
    port=settings.CHROMA_PORT,
)

# ── OpenAI 임베딩 함수 ────────────────────────────────────────────────────────
# 저장(service.py)과 검색(search_internal_db) 양쪽에서 동일한 EF를 써야
# 벡터 공간이 일치해 올바른 유사도 계산이 가능함.
# ChromaDB는 EF를 영속 저장하지 않으므로 get할 때마다 명시해야 함.
_openai_ef = OpenAIEmbeddingFunction(
    api_key=settings.OPENAI_API_KEY,
    model_name="text-embedding-3-small",
)

llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)

# --- 도구 정의 ---
# react_agent에 bind되어 LLM이 필요에 따라 호출함.
# @tool 데코레이터가 함수 시그니처와 docstring을 LLM용 tool_schema로 변환함.


@tool
async def search_past_meetings(
    query: str, meeting_ids: Optional[list[int]] = None
) -> list:
    """
    이전 회의 내용에서 관련 정보를 검색한다.
    meeting_ids: 검색 대상 회의 ID 목록. None 또는 빈 배열이면 전체 회의 검색.
    """
    try:
        # meeting_ids가 있으면 해당 회의만 검색
        match_filter = {}
        if meeting_ids:
            match_filter["meeting_id"] = {"$in": [int(m) for m in meeting_ids]}

        pipeline = [
            {"$match": match_filter},
            {"$unwind": "$utterances"},
            {"$sort": {"utterances.seq": 1}},
            {"$limit": 8},
        ]
        cursor = mongo_db["utterances"].aggregate(pipeline)
        docs = await cursor.to_list(length=8)

        # $text 매칭 없으면 regex fallback
        if not docs:
            words = query.split()[:3]
            regex_pattern = "|".join(re.escape(w) for w in words)
            cursor = (
                mongo_db["utterances"]
                .find(
                    {**match_filter, "content": {"$regex": regex_pattern}}, {"_id": 0}
                )
                .limit(8)
            )
            docs = await cursor.to_list(length=8)

        return [
            {
                "source": "past_meetings",
                "title": f"[이전회의 meeting_id={doc.get('meeting_id')}] {doc['utterances'].get('speaker_label', '?')}",
                # snippet = 실제 발화 원문 → LLM이 이걸 citations으로 인용
                "snippet": doc["utterances"].get("text", ""),
                "url": None,
                "relevance_score": 0.5,
            }
            for doc in docs
        ]
    except Exception:
        return []


@tool
def search_internal_db(
    query: str, workspace_id: int, document_name: Optional[str] = None
) -> list:
    """
    회사 내부 문서(업로드 파일, 회의록, 보고서)에서 관련 정보를 시멘틱 검색한다.
    workspace_id: 현재 워크스페이스 ID
    document_name: 특정 문서명 지정 시 해당 문서 내에서만 검색
    """
    try:
        # get_collection()이 저장 때와 동일한 EF를 사용 → 벡터 공간 일치
        collection = get_collection(workspace_id)
        count = collection.count()
        if count == 0:
            return []

        where = None
        if document_name:
            where = {"title": {"$contains": document_name}}

        results = collection.query(
            query_texts=[query],
            n_results=min(
                5, count
            ),  # count < 5 이면 ChromaDB InvalidArgumentError 방지
            where=where,
        )

        return [
            {
                "source": "internal_db",
                "source_type": meta.get(
                    "source_type", "uploaded"
                ),  # uploaded | meeting_minutes | report
                "title": meta.get("title") or "내부 문서",
                "snippet": doc,
                "url": meta.get("url", None),
                # ChromaDB distance는 가까울수록 0에 가까움 -> 1에서 빼서 socre로 변환
                "relevance_score": 1 - distance,  # ChromaDB distance -> score 변환
            }
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]
    except Exception:
        return []


@tool
def get_document_full_content(document_name: str, workspace_id: int) -> str:
    """
    특정 문서의 전체 내용을 순서대로 반환한다.
    "X 요약해줘", "X 전체 내용 알려줘"처럼 특정 문서 전체가 필요할 때 사용
    search_internal_db는 유사도 기반 일부만 반환하므로, 문서 전체가 필요한 경우 이 도구를 사용.
    """
    try:
        collection = get_collection(workspace_id)
        results = collection.get(include=["documents", "metadatas"])
        all_docs = results.get("documents", [])
        all_metadatas = results.get("metadatas", [])

        # title 또는 filename에 document_name 포함되는 청크 필터링
        matching = [
            (doc, meta)
            for doc, meta in zip(all_docs, all_metadatas)
            if document_name.lower() in (meta.get("title") or "").lower()
            or document_name.lower() in (meta.get("filename") or "").lower()
        ]
        if not matching:
            return ""

        # chunk_index 순으로 정렬 -> 문서 원래 순서 유지
        matching.sort(key=lambda x: x[1].get("chunk_index", 0))
        title = matching[0][1].get("title") or document_name
        return f"[{title}]\n\n" + "\n\n".join(doc for doc, _ in matching)
    except Exception:
        return ""


# Tavily 웹검색 도구
web_search = TavilySearchResults(
    max_results=5,
    tavily_api_key=settings.TAVILY_API_KEY,
)

tools = [
    web_search,
    search_past_meetings,
    search_internal_db,
    get_document_full_content,
]


def _fmt_citation(c: str) -> str:
    lines = [l for l in c.split("\n") if l.strip()]
    return "\n".join(f"> {l}" for l in lines) if lines else f"> {c}"


# --- ReAct Agent 그래프 (ToolNode 방식) ---
# llm_with_tools: LLM이 tool_schema 목록을 인식하고 필요 시 tool_call을 생성할 수 있게 바인딩.
llm_with_tools = llm.bind_tools(tools)


def agent_node(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


agent_graph = StateGraph(MessagesState)
agent_graph.add_node("agent", agent_node)
agent_graph.add_node("tools", ToolNode(tools))
agent_graph.set_entry_point("agent")
agent_graph.add_conditional_edges("agent", tools_condition)
agent_graph.add_edge("tools", "agent")

react_agent = agent_graph.compile()


def _select_history(history: list[dict], max_chars: int = 6000) -> list[dict]:
    """최근 메시지부터 역순으로 토큰 예산 내에서 선택"""
    selected = []
    total = 0
    for msg in reversed(history):
        length = len(msg.get("content", ""))
        if total + length > max_chars:
            break
        selected.insert(0, msg)
        total += length
    return selected


async def _resolve_references(question: str, history: list[dict], llm) -> str:
    """이전 대화를 참고해 지시어・대명사를 구체적 표현으로 치환."""
    if not history:
        return question
    if not any(
        w in question
        for w in [
            "그",
            "거기",
            "아까",
            "이전",
            "저번",
            "해당",
            "그것",
            "그분",
            "그 회의",
            "그 업무",
        ]
    ):
        return question

    history_text = "\n".join(
        f"[{m['role']}] {m['content'][:150]}" for m in history[-4:]
    )
    prompt = f"""
    이전 대화를 참고해 현재 질문의 지시어・대명사를 구체적 표현으로 바꾸세요.
    바꿀 필요 없으면 그대로 출력하세요. 질문만 출력하세요.

    이전 대화:
    {history_text}

    현재 질문: {question}
    """
    try:
        result = await llm.ainvoke(prompt)
        resolved = result.content.strip()
        return resolved if resolved else question
    except Exception:
        return question


# --- LangGraph 노드 함수들 ---
# SharedState를 받아 처리 후 업데이트할 필드만 dict로 반환.
# LangGraph가 반환값을 state에 머지(merge)한다.


async def knowledge_node(state: SharedState) -> dict:
    """
    사용자 질문을 react_agent로 처리하는 메인 Q&A 노드.

    흐름:
        react_agent 호출
        도구 사용 여부에 따라 분기:
            - 도구 사용 (웹검색/캘린더/내부문서) -> citation 검증 생략
            - 회의 내용 기반 -> citation이 원문에 실제 존재하는지 검증
    """
    workspace_id = state.get("workspace_id", "")
    meeting_id = state.get("meeting_id")
    past_meeting_ids = state.get("past_meeting_ids")
    user_id = state.get("user_id")
    is_admin = state.get("is_admin", False)
    session_id = state.get("session_id")
    original_question = state["user_question"]

    # MongoDB에서 후처리 완료된 발화 로드
    transcript_text = ""
    if meeting_id:
        ctx_doc = await mongo_db["utterances"].find_one(({"meeting_id": meeting_id}))
        if ctx_doc and ctx_doc.get("utterances"):
            transcript_text = "\n".join(
                f"[{u.get('speaker_label', '?')}] {u.get('content', '')}"
                for u in ctx_doc["utterances"]
            )
    no_meeting_context = not transcript_text.strip()

    # 이전 대화 로드 + 토큰 예산 선택
    from app.domains.knowledge.repository import get_chat_history

    history = await get_chat_history(workspace_id, session_id)
    recent_history = _select_history(history)

    # 지시어 해소 (온톨로지 추출 정확도 향상)
    resolved_question = await _resolve_references(
        original_question, recent_history, llm
    )

    # 온톨로지 컨텍스트 프리패치
    from app.core.ontology import build_ontology_context

    ontology_ctx = await build_ontology_context(resolved_question, workspace_id, llm)

    # 권한 힌트
    if is_admin:
        permission_hint = "이 사용자는 관리자입니다. 모든 데이터 접근 가능."
    elif user_id:
        permission_hint = f"이 사용자(user_id={user_id})는 일반 멤버입니다."
    else:
        permission_hint = "권한 정보 없음."

    # 이전 회의 필터 힌트
    if past_meeting_ids:
        ids_str = ", ".join(f'"{i}"' for i in past_meeting_ids)
        meeting_filter_hint = (
            f"\n선택된 이전 회의 ID: [{ids_str}]."
            f"search_past_meetings 호출 시 meeting_ids 인자로 반드시 전달하세요."
        )
    else:
        meeting_filter_hint = "\nsearch_past_meetings 호출 시 meeting_ids는 null로 전달하세요. (전체 검색)"

    system_prompt = f"""
    당신은 회의 AI 어시스턴트입니다.

    [접근 권한]
    {permission_hint}

    [사전 조회된 관련 정보 - 온톨로지 그래프]
    {ontology_ctx if ontology_ctx else "(없음)"}
    위 정보로 충분히 답할 수 있으면 도구 호출 없이 바로 답변하세요.
    
    규칙:
    - 특정 문서를 요약하거나 전체 내용이 필요할 때 → get_document_full_content 사용. workspace_id는 반드시 "{workspace_id}". 
    - 사용자 질문에 파일명·문서명이 포함되어 있으면 get_document_full_content를 가장 먼저 호출하세요.  
    - 여러 문서에 걸친 키워드·개념 검색 → search_internal_db 사용. workspace_id는 반드시 "{workspace_id}". 
    - 사용자 질문에 파일명·문서명·자료명이 포함되어 있으면 반드시 get_document_full_content를 가장 먼저 호출하세요. search_internal_db보다 항상 우선합니다.                                                                    
    - get_document_full_content 도구를 사용했으면 citations는 반드시 []. 문서 내용 자체가 답변이므로 별도 인용 불필요.
    - search_internal_db는 여러 문서에 걸친 키워드·개념 검색에만 사용하세요
    - 현재 회의 발화가 없거나("(없음)"), 질문이 문서·파일·보고서·업로드된 자료에 관한 것이면 search_internal_db를 반드시 먼저 사용하세요. workspace_id는 반드시 "{workspace_id}"로 전달하세요.
    - 회의 내용만으로 답할 수 있으면 도구 없이 답변하세요.
    - 정보가 불완전하더라도 회의에서 언급된 내용을 바탕으로 최대한 답변하세요.
    - 확실하지 않은 정보는 "~라고 언급됐습니다" 형식으로 답변하세요.
    - 외부 자료가 필요하면 web_search를 사용하세요.
    - 이전 회의 내용이 필요하면 search_past_meetings를 사용하세요.
    
    최종 답변은 반드시 아래 JSON 형식으로만 출력하세요.
    {{
        "answer": "사용자 질문에 대해 마크다운 형식으로 작성된 답변",
        "confidence": "high" | "medium" | "low"
        "hedge_note": "근거 있음 | 근거 불충분 | 근거 없음",
        "citations": ["근거가 된 발화를 [화자명] 내용 형식 그대로 복사. 요약・재서술 금지. 최대 3개."]
        "action_button": {{"label": "버튼 텍스트", "path": "/경로"}} | null
    }}

    confidence 기준:
    - high: 발화에 명확한 근거 있음
    - medium: 발화에 간접적으로 언급됨
    - Low: 발화에 근거 없거나 추측
    
    citations 규칙:
    - web_search 도구를 사용했으면 반드시 []. 절대 웹 검색 내용을 citations에 넣지 마세요.
    - search_past_meetings 도구를 사용했으면 반환된 snippet 원문을 그대로 복사.
    - search_internal_db 도구를 사용했으면 반환된 snippet 원문을 그대로 복사.
    - 회의 발화 기반이면 [화자명] 발화내용 형식으로 원문 발췌.

    answer 작성 규칙:
    - # 헤딩 사용 금지. ## 이하만 사용.            
    - 목록은 마크다운 bullet(-) 또는 번호 사용
    - 표 형태 데이터는 마크다운 테이블로 표현 

    action_button 규칙:
    - WBS 수정 요청 시: {{"label": "WBS 페이지로 이동", "path": "/meetings/{meeting_id}/wbs"}}
    - 그 외: null

    {meeting_filter_hint}
    """

    # react_agent 호출 - 히스토리 주입
    history_messages = [
        {"role": msg["role"], "content": msg["content"]} for msg in recent_history
    ]
    result = await react_agent.ainvoke(
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                *history_messages,
                {"role": "user", "content": state["user_question"]},
            ]
        }
    )

    # Tavily ToolMessage에서 웹 소스 추출
    seen_urls = set()
    seen_domains = set()
    web_sources = []
    for msg in result["messages"]:
        if getattr(msg, "name", None) == "tavily_search_results_json":
            try:
                raw = (
                    json.loads(msg.content)
                    if isinstance(msg.content, str)
                    else msg.content
                )
                if isinstance(raw, list):
                    for s in raw:
                        url = s.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        domain = urlparse(url).netloc
                        if domain in seen_domains:
                            continue
                        seen_urls.add(url)
                        seen_domains.add(domain)
                        web_sources.append(
                            {
                                "title": s.get("title", ""),
                                "url": s.get("url", ""),
                                "snippet": s.get("content", "")[:200],
                            }
                        )
            except Exception:
                pass

    # 도구 사용 여부 확인 - tool_calls 있으면 웹검색/캘린더 등 외부 도구 사용한 것
    tool_used = any(getattr(msg, "tool_calls", None) for msg in result["messages"])

    # search_internal_db 사용 여부 별도 체크
    internal_db_used = any(
        tc.get("name") in ("search_internal_db", "get_document_full_content")
        for msg in result["messages"]
        for tc in (getattr(msg, "tool_calls", None) or [])
    )

    # LLM이 앞뒤에 설명 텍스트를 붙이는 경우를 대비해 JSON 블록만 추출
    raw = result["messages"][-1].content
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        parsed = {}

    answer = parsed.get("answer", raw)  # JSON 파싱 실패 시 원문 그대로 사용
    confidence = parsed.get("confidence", "low")
    citations = parsed.get("citations", [])
    action_button = parsed.get("action_button")

    if web_sources:
        pass  # 프론트엔드에서 web_sources 별도 표시

    elif tool_used:
        if web_sources:
            pass
        # search_past_meetings: 이전 회의 발화가 citations로 오면 표시
        elif citations:
            label = "📎 근거 문서:" if internal_db_used else "📎 근거 발화:"
            citation_block = f"\n\n**{label}**\n" + "\n\n".join(
                _fmt_citation(c) for c in citations
            )
            answer += citation_block

    else:
        # 발화 기반 답변 -> citation이 실제 발화 원문에 존재하는지 검증
        context_words = set(re.findall(r"[가-힣a-zA-Z0-9]", transcript_text))
        verified_citations = []
        citation_failed = False

        for c in citations:
            citation_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", c))
            overlap = (
                len(citation_words & context_words) / len(citation_words)
                if citation_words
                else 0
            )
            if overlap >= 0.6:
                verified_citations.append(c)
            else:
                # citation이 원문에 없음 -> LLM이 인용을 조작(fabrication)한 케이스
                citation_failed = True

        if citation_failed or (not citations and confidence == "low"):
            # 불일치 또는 근거 없음 -> 답변 자체를 대체
            if not tool_used and no_meeting_context:
                # 회의 없는 상태에서 도구 미사용 → 내부 문서 검색 유도
                answer = "관련 내용을 찾지 못했습니다. 해당 파일이 업로드되어 있는지 확인해주세요."
            else:
                answer = "해당 내용은 회의에서 확인되지 않았습니다."
        else:
            # 검증 통과한 citations만 표시
            if verified_citations:
                citation_block = "\n\n**📎 근거 발화:**\n" + "\n".join(
                    f"> {c}" for c in verified_citations
                )
                answer += citation_block

            # medium이면 간접 근거 고지
            if confidence == "medium":
                answer += "\n\n※ 간접적으로 언급된 내용을 바탕으로 한 답변입니다."

    return {
        "chat_response": answer,
        "function_type": "agent",
        "web_sources": web_sources,
        "action_button": action_button,
    }


async def _get_meetings_by_question(
    question: str, workspace_id: int
) -> tuple[list[dict], bool]:
    """user_question에서 날짜 범위 추출해서 MongoDB 필터링.
    반환: (meetings, has_date_range) — has_date_range=True면 날짜 조건으로 필터링된 결과.
    """
    from app.domains.knowledge.repository import get_all_past_meetings_by_workspace
    from datetime import datetime

    all_meetings = await get_all_past_meetings_by_workspace(workspace_id)

    date_prompt = f"""
    아래 질문에서 날짜 범위를 추출하세요. JSON으로만 답하세요.
    없으면 {{"start": null, "end": null}}

    질문: {question}
    현재 날짜: {now_kst().strftime("%Y-%m-%d")}

    {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}
    """
    result = await llm.ainvoke(date_prompt)
    try:
        dates = json.loads(re.search(r"\{.*\}", result.content, re.DOTALL).group())
        start = datetime.fromisoformat(dates["start"]) if dates.get("start") else None
        end = datetime.fromisoformat(dates["end"]) if dates.get("end") else None
    except Exception:
        start, end = None, None

    if start or end:
        filtered = [
            m
            for m in all_meetings
            if (not start or m.get("created_at", datetime.min) >= start)
            and (not end or m.get("created_at", datetime.max) <= end)
        ]
        return filtered, True

    return all_meetings, False


async def past_summary_node(state: SharedState) -> dict:
    """
    단일/복수 회의 요약.
    meeting_minutes.summary(MySQL) 읽어서 반환.
    단일 회의 → LLM 없이 바로 반환.
    복수 회의 → LLM으로 통합 요약.
    """
    from app.domains.knowledge.repository import (
        get_past_meetings_by_ids,
        get_past_meetings,
    )

    past_meeting_ids = state.get("past_meeting_ids")
    workspace_id = state.get("workspace_id")
    user_id = state.get("user_id")
    is_admin = state.get("is_admin", False)
    filter_user_id = None if is_admin else user_id

    if not past_meeting_ids:
        meetings, has_date = await _get_meetings_by_question(
            state.get("user_question", ""), workspace_id
        )
        if not meetings:
            meetings = await get_past_meetings(workspace_id, user_id=filter_user_id)

        # 회의가 2개 이상이고 날짜/키워드로 범위가 특정되지 않은 경우 → 선택 요청
        if len(meetings) >= 2 and not has_date:
            return {
                "chat_response": "어떤 회의를 요약할까요? 아래에서 선택해주세요.",
                "function_type": "past_summary",
            }
    else:
        # UI에서 선택된 회의만
        meetings = await get_past_meetings_by_ids(past_meeting_ids)

    if not meetings:
        return {
            "chat_response": "이전 회의 데이터가 없습니다.",
            "function_type": "past_summary",
        }

    # 단일 회의 -> LLM 없이 바로 반환
    if len(meetings) == 1:
        m = meetings[0]
        return {
            "chat_response": _format_summary_markdown(
                {"title": m["title"], "key_points": m["summary"].split("\n")}
            ),
            "function_type": "past_summary",
        }

    # 회의별 텍스트 블록 구성
    meetings_text = "\n\n".join(
        [
            f"{m.get('title', '')} ({m['created_at'].strftime('%Y-%m-%d') if hasattr(m.get('created_at'), 'strftime') else str(m.get('created_at', ''))[:10]})"
            f"\n{m.get('summary', '')}"
            for m in meetings
        ]
    )

    prompt = f"""
    다음은 {len(meetings)}개 회의의 요약입니다.
    중요한 내용을 회의별 맥락을 포함해 가독성 좋게 요약하세요.

    {meetings_text}

    마크다운 형식으로 작성하되 # 헤딩은 사용하지 마세요. ## 이하만 사용하세요.
    """

    result = await llm.ainvoke(prompt)

    return {
        "chat_response": result.content,
        "function_type": "past_summary",
    }


async def quick_report_node(state: SharedState) -> dict:
    """
    간이보고서 노드. 단일 또는 복수 회의 지원.

    흐름:
        - past_meeting_ids 있으면 복수 회의 통합 보고서
        - meeting_id 있으면 단일 회의 보고서
        - 둘 다 없으면 선택 요청 → ChatFAB selector 트리거
    """
    from app.domains.knowledge.repository import (
        get_past_meetings_by_ids,
        get_past_meeting_ids,
    )
    from app.domains.intelligence.models import Decision
    from app.domains.action.models import WbsEpic, WbsTask
    from app.domains.meeting.models import Meeting, MeetingStatus, MeetingParticipant
    from app.domains.user.models import User
    from app.infra.database.session import SessionLocal
    from sqlalchemy import asc

    meeting_id = state.get("meeting_id")
    past_meeting_ids = state.get("past_meeting_ids")
    workspace_id = state.get("workspace_id")
    user_id = state.get("user_id")
    is_admin = state.get("is_admin", False)
    filter_user_id = None if is_admin else user_id

    if past_meeting_ids:
        meetings = await get_past_meetings_by_ids(past_meeting_ids)
    elif meeting_id:
        meetings = await get_past_meetings_by_ids([meeting_id])
    else:
        all_ids = await get_past_meeting_ids(workspace_id, user_id=filter_user_id)
        meetings = await get_past_meetings_by_ids(all_ids)

    if not meetings:
        return {
            "chat_response": "보고서를 생성할 회의가 없습니다.",
            "function_type": "quick_report",
        }

    target_ids = [m["meeting_id"] for m in meetings]

    db = SessionLocal()
    try:
        # decisions 조회
        decisions = (
            db.query(Decision)
            .filter(Decision.meeting_id.in_(target_ids))
            .order_by(Decision.meeting_id, Decision.detected_at)
            .all()
        )

        # wbs_tasks 조회
        epics = db.query(WbsEpic).filter(WbsEpic.meeting_id.in_(target_ids)).all()
        epic_ids = [e.id for e in epics]
        tasks = (
            (
                db.query(WbsTask)
                .filter(WbsTask.epic_id.in_(epic_ids))
                .order_by(WbsTask.order_index)
                .all()
            )
            if epic_ids
            else []
        )

        # 회의별 참석자 조회
        attendees_by_meeting: dict[int, list[str]] = {}
        if target_ids:
            rows = (
                db.query(MeetingParticipant.meeting_id, User.name)
                .join(User, MeetingParticipant.user_id == User.id)
                .filter(MeetingParticipant.meeting_id.in_(target_ids))
                .all()
            )
            for mid, name in rows:
                attendees_by_meeting.setdefault(mid, []).append(name)

        # next_meeting 조회
        next_m = (
            db.query(Meeting.title, Meeting.scheduled_at)
            .filter(
                Meeting.workspace_id == workspace_id,
                Meeting.status == MeetingStatus.scheduled,
            )
            .order_by(asc(Meeting.scheduled_at))
            .first()
        )
        next_meeting_str = (
            f"{next_m.title} ({next_m.scheduled_at.strftime('%Y-%m-%d %H:%M')})"
            if next_m and next_m.scheduled_at
            else "일정 논의 필요"
        )
    finally:
        db.close()

    meetings_meta = [
        {
            "title": m.get("title", ""),
            "date": (
                m["created_at"].strftime("%Y-%m-%d")
                if hasattr(m.get("created_at"), "strftime")
                else str(m.get("created_at", ""))[:10]
            ),
            "summary": m.get("summary", ""),
            "attendees": attendees_by_meeting.get(m["meeting_id"], []),
        }
        for m in meetings
    ]
    decisions_text = (
        "\n".join(
            f"- [회의{d.meeting_id}] {d.content} ({'확정' if d.is_confirmed else '미확정'})"
            for d in decisions
        )
        or "(없음)"
    )
    tasks_text = (
        "\n".join(
            f"- [{t.assignee_name or '미정'}] {t.title}"
            f" / 상태: {t.status.value} / 진행률: {t.progress}%"
            f" / 우선순위: {t.priority.value} / 긴급도: {t.urgency or 'normal'}"
            f" / 기한: {t.due_date.isoformat() if t.due_date else '미정'}"
            for t in tasks
        )
        or "(없음)"
    )
    meetings_count = f"{len(meetings)}개 회의" if len(meetings) > 1 else "단일 회의"

    # 단일/복수 통합 프롬프트
    prompt = f"""
    다음은 {meetings_count} 발화/요약 내용입니다. 간이보고서를 작성하세요.

    [결정 사항]
    {decisions_text}

    [WBS 태스크]
    {tasks_text}

    [회의 정보]
    {json.dumps(meetings_meta, ensure_ascii=False)}

    [다음 예정 회의]
    {next_meeting_str}

    이전 회의 follow-up (컨텍스트에 이전 회의 내용이 있을 경우): 
    - WBS 태스크 상태가 done이면 → pending_items에서 제외
    - 상태가 todo/in_progress이면 → pending_items에 carried_over: true로 포함                                                           
    - 결정 사항이 미확정이면 → pending_items에 포함 

    단일 회의면 meetings 배열에 1개, 복수면 회의별로 각각 포함

    반드시 아래 JSON 형식으로만 답변하세요.

    {{                                                                                                               
        "meetings": [{{"title": "회의 제목", "date": "일시", "attendees": ["참석자1", ...]}}],
        "overview_summary": "전체 내용 요약",                   
        "agenda_items": ["주요 안건1", "주요 안건2" ...],
        "discussion_items": [{{"topic": "주제명", "content": "구체적으로 논의된 내용"}}, ...],
        "decisions": ["최종 결론/결정 사항", ...],
        "action_items": [{{"assignee": "담당자 or null", "content": "할 일", "deadline": "기한 or null", "urgency": "urgent|normal|low", "priority": "high|normal"}}, ...],
        "pending_items": [{{"content": "미결 사항", "carried_over": false}}, ...],
        "next_meeting": "{next_meeting_str}",
        "next_meeting_agenda": ["다음 회의 안건", ...],
        "hallucination_flags": [...]                                    
      }} 
    """
    result = await llm.ainvoke(prompt)
    json_match = re.search(r"\{.*\}", result.content, re.DOTALL)
    try:
        report_dict = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        report_dict = {}

    return {
        "chat_response": _format_quick_report_markdown(report_dict),
        "function_type": "quick_report",
        "hallucination_flags": report_dict.get("hallucination_flags", []),
    }


async def report_guide_node(state: SharedState) -> dict:
    return {
        "chat_response": "정식 보고서는 회의록 페이지에서 생성할 수 있습니다.",
        "function_type": "report_guide",
    }


def _format_summary_markdown(s: dict) -> str:
    """summary_dict → 프론트엔드 표시용 마크다운 문자열 변환."""
    lines = []
    meetings = s.get("meetings", []) or []

    # 복수 회의면 목록 헤더, 단일이면 해당 회의 제목
    if len(meetings) > 1:
        lines.append("## 📋 이전 회의 종합 요약")
        for m in meetings:
            lines.append(f"- **{m.get('title', '')}** ({m.get('date', '')})")
    elif len(meetings) == 1:
        lines.append(f"## 📋 {meetings[0].get('title', '회의 요약')}")
    else:
        lines.append(f"## 📋 {s.get('title') or '회의 요약'}")

    for point in s.get("key_points", []) or []:
        lines.append(f"- {point}")

    return "\n".join(lines)


def _format_quick_report_markdown(s: dict) -> str:
    """quick_report_node → 전체 구조 보고서 포맷."""
    lines = []
    meetings = s.get("meetings", []) or []

    if len(meetings) > 1:
        lines.append("## 📋 이전 회의 종합 보고서")
        for m in meetings:
            attendees_str = (
                f" ({', '.join(m['attendees'])})" if m.get("attendees") else ""
            )
            lines.append(
                f"- **{m.get('title', '')}** {m.get('date', '')}{attendees_str}"
            )
    else:
        m = meetings[0] if meetings else {}
        lines.append(f"## 📋 {m.get('title') or s.get('title') or '간이보고서'}")
        if m.get("date"):
            lines.append(f"**일시:** {m['date']}")
        if m.get("attendees"):
            lines.append(f"**참석자:** {', '.join(m['attendees'])}")

    if s.get("overview_summary"):
        lines.append(f"\n**회의 내용 요약**\n{s['overview_summary']}")

    if s.get("agenda_items"):
        lines.append("\n### 📌 주요 안건")
        for item in s["agenda_items"]:
            lines.append(f"- {item}")

    for i, item in enumerate(s.get("discussion_items", []) or [], 1):
        if i == 1:
            lines.append("\n### 🗂 구체적으로 논의된 사항")
        lines.append(f"\n**{i}. {item.get('topic', '')}**")
        lines.append(item.get("content", ""))

    if s.get("decisions"):
        lines.append("\n### ✅ 최종 결론")
        for d in s["decisions"]:
            lines.append(f"- {d if isinstance(d, str) else d.get('decision', '')}")

    if s.get("action_items"):
        lines.append("\n### 📋 할 일\n")
        lines.append("| 담당자 | 내용 | 기한 | 긴급도 |")
        lines.append("|---|---|---|---|")
        urgency_label = {"urgent": "🔴 긴급", "normal": "⚠️  보통", "low": "🟢 낮음"}
        for a in s["action_items"]:
            lines.append(
                f"| {a.get('assignee') or '미정'} | {a.get('content', '')} "
                f"| {a.get('deadline') or '-'} | {urgency_label.get(a.get('urgency', 'low'), '-')} |"
            )

    if s.get("pending_items"):
        lines.append("\n### 🔁 미결 사항")
        for p in s["pending_items"]:
            text = p if isinstance(p, str) else p.get("content", "")
            suffix = (
                " _(이전 회의 연속)_"
                if isinstance(p, dict) and p.get("carried_over")
                else ""
            )
            lines.append(f"- {text}{suffix}")

    next_date = s.get("next_meeting")
    if next_date in ("null", "None", "없음", ""):
        next_date = "일정 논의 필요"

    next_agenda = s.get("next_meeting_agenda", []) or []
    if next_agenda or next_date is not None:
        lines.append("\n### 🔜 다음 회의에서 다룰 내용")
        lines.append(f"**일정:** {next_date if next_date else '미정'}")
        for item in next_agenda:
            lines.append(f"- {item}")

    return "\n".join(lines)


async def classify_intent(state: SharedState) -> dict:
    """summary 여부만 판단 - 나머지는 전부 knowledge_node로"""
    prompt = f"""
    사용자 입력을 아래 4가지 중 하나로 분류하세요. 단어 하나만 출력하세요.

    - past_summary: **회의** 내용을 요약해달라는 요청. 반드시 "회의"가 주어여야 함.
        예) "이전 회의 요약해줘", "지난 회의 정리해줘", "전 회의 내용 요약", "N월 회의 요약", "4월 1일부터 현재까지 회의 요약"
        비고: 문서·파일·보고서 이름이 주어인 요약 요청은 past_summary가 아님.
    - quick_report: 간이보고서/보고서 생성 요청 (형식 미지정 또는 간단 정리).
        예) "간이보고서 만들어줘", "보고서 만들어줘", "회의 보고서 생성해줘"
    - report_guide: 특정 파일 포맷 보고서 요청 (Excel·PDF·HTML·다운로드 등).
        예) "Excel로 저장", "HTML 보고서", "보고서 다운로드", "PDF로 내보내기", "회의록 파일로 저장"
    - agent: 문서·파일 내용 조회, 외부 정보 검색, 일정 관련, DB 조회, 그 외 모든 입력.
        예) "AI 브리프 내용 요약해줘", "AI브리프 3월 전체 내용 요약해줘", "~~문서 요약해줘", "지난 회의에서 결정된 거 알려줘", "오늘 일정 알려줘"

    입력: {state['user_question']}
    """
    result = await llm.ainvoke(prompt)
    function_type = result.content.strip().lower()
    # LLM이 예상 밖의 값을 반환하면 agent로 fallback
    if function_type not in (
        "summary",
        "past_summary",
        "quick_report",
        "report_guide",
        "agent",
    ):
        function_type = "agent"
    return {"function_type": function_type}


def get_collection(workspace_id: str):
    f"""
    ws_{workspace_id}_docs 컬렉션 반환.
    service.py(저장)와 search_internal_db(검색) 양쪽에서 호출.
    항상 동일한 _openai_ef를 넘겨 벡터 공간 일치 보장.
    """
    return chroma_client.get_or_create_collection(
        name=f"ws_{workspace_id}_docs",
        embedding_function=_openai_ef,
        metadata={"workspace_id": workspace_id},
    )
