import json
import re
from typing import Optional
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, MessagesState, END
from motor.motor_asyncio import AsyncIOMotorClient
import chromadb
import redis

from app.core.config import settings
from app.core.graph.state import SharedState
from app.utils.redis_utils import get_meeting_context, is_meeting_live
from app.utils.time_utils import now_kst
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# --- 클라이언트 초기화 ---
# 모듈 로드 시 한 번만 연결. 요청마다 새로 연결하지 않음.
mongo_db = AsyncIOMotorClient(settings.MONGODB_URL)["workb"]
chroma_client = chromadb.HttpClient(
    host=settings.CHROMA_HOST,
    port=settings.CHROMA_PORT,
)
r = redis.asyncio.from_url(settings.REDIS_URL)

# ── OpenAI 임베딩 함수 ────────────────────────────────────────────────────────
# 저장(service.py)과 검색(search_internal_db) 양쪽에서 동일한 EF를 써야
# 벡터 공간이 일치해 올바른 유사도 계산이 가능함.
# ChromaDB는 EF를 영속 저장하지 않으므로 get할 때마다 명시해야 함.
_openai_ef = OpenAIEmbeddingFunction(
    api_key=settings.OPENAI_API_KEY,
    model_name="text-embedding-3-small",
)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.OPENAI_API_KEY
)

# --- 도구 정의 ---
# react_agent에 bind되어 LLM이 필요에 따라 호출함.
# @tool 데코레이터가 함수 시그니처와 docstring을 LLM용 tool_schema로 변환함.

@tool
async def search_past_meetings(query: str, meeting_ids: Optional[list[str]] = None) -> list:
    """
    이전 회의 내용에서 관련 정보를 검색한다.
    meeting_ids: 검색 대상 회의 ID 목록. None 또는 빈 배열이면 전체 회의 검색.
    """
    try:
        # meeting_ids가 있으면 해당 회의만 검색
        base_filter = {}
        if meeting_ids:
            base_filter["meeting_id"] = {"$in": meeting_ids}

        # $text 검색 시도 $meta 연산자를 사용하여 텍스트 검색 결과를 점수 순으로 정렬
        cursor = mongo_db["meeting_contexts"].find(
            {**base_filter, "$text": {"$search": query}},
            {"score": {"$meta": "textScore"}}, # 점수를 'score' 필드에 저장
        ).sort([("score", {"$meta": "textScore"})]).limit(5) # 점수 순으로 정렬
        docs = await cursor.to_list(length=5)

        # $text 매칭 없으면 base_filter 범위 내에서 최신순 fallback
        if not docs:
            cursor = mongo_db["meeting_contexts"].find(
                base_filter, {"_id": 0}
            ).sort("created_at", -1).limit(5)
            docs = await cursor.to_list(length=5)

        return [
            {
                "source": "past_meetings",
                "title": doc.get("title", "이전 회의"),
                "snippet": doc.get("summary", ""),
                "url": None,
                "relevance_score": doc.get("score", 0.5)
            }
            for doc in docs
        ]
    except Exception:
        return []

@tool
def search_internal_db(query: str, workspace_id: str) -> list:
    """
    회사 내부 문서에서 관련 정보를 시멘틱 검색한다.
    workspace_id: 현재 워크스페이스 ID
    """
    try:
        # get_collection()이 저장 때와 동일한 EF를 사용 → 벡터 공간 일치
        collection = get_collection(workspace_id)
        results = collection.query(
            query_texts=[query],
            n_results=5
        )
        return [
            {
                "source": "internal_db",
                "title": meta.get("title", "내부 문서"),
                "snippet": doc,
                "url": meta.get("url", None),
                # ChromaDB distance는 가까울수록 0에 가까움 -> 1에서 빼서 socre로 변환
                "relevance_score": 1 - distance # ChromaDB distance -> score 변환
            }
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )
        ]
    except Exception:
        return []

@tool
def register_calendar(
    title: str,
    start: str,
    end: str = "",
    description: str = "",
    location: str = ""
) -> dict:
    """
    Google Calendar에 일정을 등록한다.
    start/end 형식: 2026-04-15T14:00:00:+09:00
    """    
    # Todo: 추후 Google Calendar 모듈 연결
    return {
        "status": "registered",
        "title": title,
        "start": start,
        "end": end,
    }

@tool
def update_calendar_event(
    event_id: str,
    title: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = ""
) -> dict:
    """
    Google Calendar 일정을 수정합니다.
    event_id는 필수, 나머지는 변경할 항목만 입력
    """
    # Todo: 추후 Google Calendar 모듈 연결
    return {"status": "updated", "event_id": event_id}

@tool
def delete_calendar_event(event_id: str) -> dict:
    """Google Calendar 일정을 삭제합니다."""
    # Todo: 추후 Google Calendar 모듈 연결
    return {"status": "deleted", "event_id": event_id}

@tool
def get_calendar_events(
    date: str = "",
    event_id: str = ""
) -> list:
    """
    Google Calendar 일정을 조회합니다.
    date 형식: 2026-04-15, event_id는 필수
    date만 입력하면 해당 날짜의 모든 일정을 반환한다.
    """
    # Todo: 추후 Google Calendar 모듈 연결
    return []

# Tavily 웹검색 도구
web_search = TavilySearchResults(
    max_results=5,
    tavily_api_key=settings.TAVILY_API_KEY,
)

tools = [
    web_search, 
    search_past_meetings, 
    search_internal_db, 
    register_calendar,
    update_calendar_event,
    delete_calendar_event,
    get_calendar_events
]

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

# --- LangGraph 노드 함수들 ---
# SharedState를 받아 처리 후 업데이트할 필드만 dict로 반환.
# LangGraph가 반환값을 state에 머지(merge)한다.

async def knowledge_node(state: SharedState) -> dict:
    """
    사용자 질문을 react_agent로 처리하는 메인 Q&A 노드.

    흐름:
        1. 회의 중 여부 확인 (is_live) - STT 딜레이 고지 여부 결정
        2. 현재 회의 발화 로드 (meeting_id 있을 때만)
        3. react_agent 호출
        4. 도구 사용 여부에 따라 분기:
            - 도구 사용 (웹검색/캘린더/내부문서) -> citiation 검증 생략
            - 회의 내용 기반 -> citiation이 원문에 실제 존재하는지 검증
        5. STT 딜레이 고지 prepend (회의 중일 때만)
    """
    meeting_id = state.get("meeting_id")
    # Redis utterances 존재 여부로 회의 중/후 판단
    is_live = await is_meeting_live(meeting_id) if meeting_id else False
    meeting_context = await get_meeting_context(meeting_id) if meeting_id else ""
    workspace_id = state.get("workspace_id", "")
    past_meeting_ids = state.get("past_meeting_ids")

    if past_meeting_ids:
        ids_str = ", ".join(f'"{i}"' for i in past_meeting_ids)
        meeting_filter_hint = (
            f"\n선택된 이전 회의 ID: [{ids_str}]."
            f"search_past_meetings 호출 시 meeting_ids 인자로 반드시 전달하세요."
        )
    else:
        meeting_filter_hint = (
            "\nsearch_past_meetings 호출 시 meeting_ids는 null로 전달하세요. (전체 검색)"
        )

    system_prompt = f"""
    당신은 회의 AI 어시스턴트입니다.

    현재 회의 발화 내용:
    {meeting_context}
    
    규칙:
    - 회의 내용만으로 답할 수 있으면 도구 없이 답변하세요.
    - 정보가 불완전하더라도 회의에서 언급된 내용을 바탕으로 최대한 답변하세요.
    - 확실하지 않은 정보는 "~라고 언급됐습니다" 형식으로 답변하세요.
    - 특정 문서·파일·자료·브리프·보고서 내용이 필요하면 search_internal_db를 먼저 사용하세요. workspace_id는 반드시 "{workspace_id}"로 전달하세요.
    - 외부 자료가 필요하면 web_search를 사용하세요.
    - 이전 회의 내용이 필요하면 search_past_meetings를 사용하세요.
    - 회사 내부 문서가 필요하면 search_internal_db를 사용하세요. workspace_id는 반드시 "{workspace_id}"로 전달하세요.

    최종 답변은 반드시 아래 JSON 형식으로만 출력하세요.
    {{
        "answer": "사용자 질문에 대한 답변",
        "confidence": "high" | "medium" | "low"
        "hedge_note": "근거 있음 | 근거 불충분 | 근거 없음",
        "citations": ["근거가 된 발화를 [화자명] 내용 형식 그대로 복사. 요약・재서술 금지. 최대 3개."]
    }}

    confidence 기준:
    - high: 발화에 명확한 근거 있음
    - medium: 발화에 간접적으로 언급됨
    - Low: 발화에 근거 없거나 추측
    citations: 도구 사용 결과나 외부 정보면 []. 회의 내용 기반이면 반드시 원문 발췌.

    {meeting_filter_hint}
    """

    result = await react_agent.ainvoke({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["user_question"]}
        ]
    })

    # 도구 사용 여부 확인 - tool_calls 있으면 웹검색/캘린더 등 외부 도구 사용한 것
    tool_used = any(
        getattr(msg, "tool_calls", None)
        for msg in result["messages"]
    )

    # LLM이 앞뒤에 설명 텍스트를 붙이는 경우를 대비해 JSON 블록만 추출
    raw = result["messages"][-1].content
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        parsed = {}

    answer = parsed.get("answer", raw) # JSON 파싱 실패 시 원문 그대로 사용
    confidence = parsed.get("confidence", "low")
    citations = parsed.get("citations", [])

    if tool_used:
        # 외부 도구 사용 결과 -> 발화 원문과 대조 불필요, 검증 생략
        pass
    else:
        # 회의 내용 기반 답변 -> citation이 실제 발화 원문에 존재하는지 검증
        context_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", meeting_context))
        verified_citations = []
        citation_failed = False

        for c in citations:
            citation_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", c))
            overlap = len(citation_words & context_words) / len(citation_words) if citation_words else 0
            if overlap >= 0.6:
                verified_citations.append(c)
            else:
                # citation이 원문에 없음 -> LLM이 인용을 조작(fabrication)한 케이스
                citation_failed = True

        if citation_failed or (not citations and confidence == "low"):
            # 불일치 또는 근거 없음 -> 답변 자체를 대체
            answer = "해당 내용은 회의에서 확인되지 않았습니다."
        else:
            # 검증 통과한 citations만 표시
            if verified_citations:
                citation_block = "\n\n**📎 근거 발화:**\n" + "\n".join(f"> {c}" for c in verified_citations)
                answer += citation_block
            
            # medium이면 간접 근거 고지
            if confidence == "medium":
                answer += "\n\n※ 간접적으로 언급된 내용을 바탕으로 한 답변입니다."

    # STT 딜레이 고지 - Redis utterances 있는 경우(회의 중)에만 prepend
    if is_live:
        answer = (
            "※ 아래는 약 30초 전까지 반영된 발화 기준이며, 가장 최근 발화는 포함되지 않을 수 있습니다.\n\n"                
            + answer 
        )

    return {
        "chat_response": answer,
        "function_type": "agent"
    }

async def summary_node(state: SharedState) -> dict:
    """
    회의 발화 전체를 구조화된 JSON 요약으로 변환하는 노드.

    흐름:
        1. 컨텍스트 로드 - partial_summary 캐시 우선, 없으면 전체 발화
        2. 이전 회의 데이터 조회 - follow-up 추적에 사용
        3. 프롬프트 구성
        4. LLM 호출 - SummaryResponse 구조 강제
        5. 할루시네이션 검증 - 발화 키워드 겹침률로 신뢰도 판정
    """
    meeting_id = state.get("meeting_id")
    is_live = await is_meeting_live(meeting_id) if meeting_id else False
    past_meeting_ids = state.get("past_meeting_ids")

    # 1단계: 컨텍스트 로드
    # partial_summary가 있으면 이미 요약된 앞부분은 재처리하지 않고 재사용.
    # 없으면 Redis에서 전체 발화를 가져온다.
    if not meeting_id:
        context = ""
    else:
        cached = await r.get(f"meeting:{meeting_id}:partial_summary")
        if cached:
            # 이전 partial_summary + 새 발화만 이어붙여 중분 처리
            prev_summary = cached.decode()
            new_utterances = await get_meeting_context(meeting_id)
            context = f"[이전 요약]\n(prev_summary)\n\n[추가 발화]\n{new_utterances}"
        else:
            context = await get_meeting_context(meeting_id)

    # 2단계: 이전 회의 데이터 조회
    # past_meeting_ids 있으면 선택된 회의만, 없으면 전체 검색
    past_meetings = await search_past_meetings.ainvoke({
        "query": context[:200],
        "meeting_ids": past_meeting_ids if past_meeting_ids else None,
    })
    past_context = "\n".join(
        m.get("snippet", "") for m in past_meetings if m.get("snippet")
    )

    # 3단계: 프롬프트 구성
    # 발화 흐름에서 자연스럽게 묶이는 주제를 LLM이 직접 판단해 클러스터링
    discussion_guide = """
    주요 논의 사항은 발화 내용을 분석해 자연스럽게 클러스터링된 주제별로 작성하세요.
    주제명(topic)은 발화 맥락을 대표하는 간결한 명사구로 작성하세요.
    """

    # 화자분리 실패 안내: "알 수 없음" / "화자N" 표기 발화 처리 지침을 LLM에 명시.
    # assignee를 null로 처리하면 잘못된 담당자 할당을 방지할 수 있다.
    speaker_note = """
    발화자 표기 중 "알 수 없음" 또는 "화자N"은 화자분리가 불완전한 발화입니다.
    - 이런 발화는 내용 중심으로 요약하세요.
    - action_items의 assignee는 반드시 null로 설정하세요. 임의로 추측하지 마세요.
    """

    prompt = f"""
    다음은 현재까지의 회의 발화 내용입니다.
    STT 처리 딜레이로 인해 최근 약 30초 이내 발화는 포함되지 않을 수 있습니다.

    [회의 발화]
    {context}

    [이전 회의 요약] (follow-up 추적에 활용)
    {past_context if past_context else "이전 회의 데이터 없음"}

    {speaker_note}

    {discussion_guide}

    액션 아이템 우선순위(priority) 판단 기준:
    - high: 결정 사항과 직접 연결 / 다른 액션의 선행 조건 / "반드시·꼭·최우선" 발화 / 다수 인원 영향
    - normal: 그 외

    긴급도(urgency) 판단 기준:
    - urgent: 기한 3일 이내 / 다음 회의 전 완료 필요 / "빨리·즉시·오늘까지·ASAP·as soon as possible" 발화
    - normal: 기한 4~7일 이내
    - low: 기한 7일 초과 또는 미언급

    이전 회의 follow-up:
    - past_meetings에서 가져온 액션 아이템이 이번 회의 발화에서 완료 언급됐으면 completed: true
    - 이번 회의에서도 미해결이면 pending_items의 carried_over: true

    decisions와 action_items의 citation: 근거 발화를 [화자명] 내용 형식 그대로 복사.
    요약・재서술 금지. 근거 발화 없으면 null.

    반드시 아래 JSON 형식으로만 답변하세요. 내용이 없는 섹션은 [] 또는 null. "없음" 텍스트 사용 금지.

    {{
        "overview": {{"purpose": "...", "datetime_str": "..."}},
        "discussion_items": [{{"topic": "...", "content": "..."}}],
        "decisions": [{{"decision": "...", "citiation": "..."}}],
        "action_items": [{{"assignee": "...", "content": "...", "deadline": "...", "priority": "high|normal", "urgency": "urgent|normal|low", "citiation": "..."}}],
        "pending_items": [{{"content": "...", "carried_over": false, "first_mentioned_meeting": null}}],
        "next_meeting": "...",
        "previous_followups": [{{"previous_action": "...", "completed": false}}],
        "hallucination_flags": []
    }}
    """

    # 4단계: LLM 호출
    result = await llm.ainvoke(prompt)
    content = result.content

    # JSON 블록만 추출 (LLM이 설명 텍스트를 앞뒤에 붙이는 경우 대비)
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    try:
        summary_dict = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        summary_dict = {}

    # 5단계: 할루시네이션 검증
    # 발화 원문에서 추출한 단어 집합과 요약 항목의 단어 겹침률을 계산.
    # 겹침률 >= 0.4이면 발화 근거가 충분하다고 판단해 "verified".
    # 임계값을 낮게 설정한 이유: 요약은 필연적으로 압축·재서술되므로
    # 단어 완전 일치를 기대하기 어렵다.
    context_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", context))
    flags = []

    # 검증 대상: decisions + action_items (요약 중 사실 관계 오류가 가장 치명적인 섹션)
    check_targets = [
        (d.get("decision", ""), d.get("citiation", "")) 
        for d in summary_dict.get("decisions", [])
    ] + [
        (a.get("content", ""), a.get("citiation", "")) 
        for a in summary_dict.get("action_items", [])
    ]

    for item_text, citation in check_targets:
        if not item_text:
            continue

        if not citation:
            confidence = "needs_review" # 근거 발화 미제출
        else:
            citation_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", citation))
            overlap = len(citation_words & context_words) / len(citation_words) if citation_words else 0
            confidence = "verified" if overlap >= 0.4 else "needs_review"

        flags.append({
            "item": item_text,
            "citiation": citation,
            "confidence": confidence,
        })

    summary_dict["hallucination_flags"] = flags

    # 6단계: 참석자 명단 DB에서 직접 주입                                                                              
    # LLM 추출 대신 DB 사용 — 발화 기반 추출 시 누락/오인식 가능                                                                        
    from app.domains.knowledge.repository import get_meeting_participants                                                
    summary_dict["attendees"] = get_meeting_participants(meeting_id) if meeting_id else []

    # 7단계 partial_summary 캐시 갱신
    # 다음 요약 호출 시 이미 처리한 내용을 재처리하지 않기 위해 저장.
    # 회의 종료 후 삭제됨
    try:
        overview = summary_dict.get("overview", {})
        partial_text = overview.get("purpose", "") or json.dumps(
            summary_dict.get("discussion_items", [])[:2], ensure_ascii=False
        )
        await r.set(f"meeting:{meeting_id}:partial_summary", partial_text)
    except Exception:
        pass  # 캐시 저장 실패는 요약 결과에 영향 없음

    formatted = _format_summary_markdown(summary_dict)
    if is_live:
        formatted = (
            "※ 아래는 약 30초 전까지 반영된 발화 기준이며, 가장 최근 발화는 포함되지 않을 수 있습니다.\n\n"                
            + formatted 
        )

    return {
        "summary": summary_dict,
        "chat_response": formatted,
        "function_type": "summary"
    }

async def _get_meetings_by_question(question: str, workspace_id: int) -> tuple[list[dict], bool]:
    """user_question에서 날짜 범위 추출해서 MongoDB 필터링.
    반환: (meetings, has_date_range) — has_date_range=True면 날짜 조건으로 필터링된 결과.
    """
    from app.domains.knowledge.repository import get_all_past_meetings_by_workspace
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
        start = now_kst().fromisoformat(dates["start"]) if dates.get("start") else None
        end = now_kst().fromisoformat(dates["end"]) if dates.get("end") else None
    except Exception:
        start, end = None, None

    if start or end:
        filtered = [
            m for m in all_meetings
            if (not start or m.get("created_at", now_kst().min) >= start)
            and (not end or m.get("created_at", now_kst().max) <= end)
        ]
        return filtered, True

    return all_meetings, False

async def past_summary_node(state: SharedState) -> dict:
    """
    선택된 이전 회의들을 하나의 구조화된 요약으로 합치는 노드.

    흐름:
        1. past_meeting_id로 MongoDB에서 회의 데이터 조회
        2. 여러 회의 텍스트를 LLM으로 통합 구조화
        3. _format_sammary_markdown으로 마크다운 변환
    """
    from app.domains.knowledge.repository import get_past_meetings_by_ids

    past_meeting_ids = state.get("past_meeting_ids")
    workspace_id = state.get("workspace_id")

    if not past_meeting_ids:
        # 날짜 범위가 있는 경우만 자동 검색
        meetings, has_date_range = await _get_meetings_by_question(state.get("user_question", ""), workspace_id)

        # 날짜 범위도 없이 전체가 나오는 건 의도한 동작이 아님
        if not has_date_range:
            return {
                "chat_response": "어떤 회의를 요약할지 선택해주세요.",
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

    # 회의 메타 정보를 미리 구성해서 프롬프트에 직접 주입
    meetings_meta = [
        {
            "meeting_id": m["meeting_id"],
            "title": m.get("title", ""),
            "date": (
                m.get("created_at").strftime("%Y-%m-%d")
                if hasattr(m.get("created_at"), "strftime")
                else str(m.get("created_at", ""))[:10]
            ),
        }
        for m in meetings
    ]
    meetings_meta_str = json.dumps(meetings_meta, ensure_ascii=False)
    dates_str = ", ".join(m["date"] for m in meetings_meta)

    # 회의별 텍스트 블록 구성
    meetings_text = "\n\n".join([
        f"[회의 {m["meeting_id"]}] {m.get("title", "")}\n{m.get('summary', '')}" 
        for m in meetings
    ])

    prompt = f"""
    다음은 {len(meetings)}개 이전 회의의 요약이다.
    모든 회의 내용을 통합하여 구조화된 JSON으로 정리하세요.

    {meetings_text}

    ㅡmeetings 필드는 반드시 아래 값을 그대로 사용하세요. (수정 금지):
    {meetings_meta_str}

    반드시 아래 JSON 형식으로만 답변하세요. 내용이 없는 섹션은 [] 또는 null.

    {{
        "meetings": {meetings_meta_str},
        "overview": {{"purpose": "이전 회의 종합 요약", "datetime_str": "{dates_str}"}},
        "discussion_items": [{{"topic": "...", "content": "..."}}],
        "decisions": [{{"decision": "...", "citiation": null}}],                                                     
        "action_items": [{{"assignee": "...", "content": "...", "deadline": "...", "priority": "high|normal", "urgency": "urgent|normal|low", "citiation": null}}],                                                                
        "pending_items": [{{"content": "...", "carried_over": false, "first_mentioned_meeting": null}}],           
        "next_meeting": null,                                                                                        
        "previous_followups": []
    }}
    """

    result = await llm.ainvoke(prompt)
    content = result.content
    
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    try:
        summary_dict = json.loads(json_match.group()) if json_match else {}
    except json.JSONDecodeError:
        summary_dict = {}

    formatted = _format_summary_markdown(summary_dict)
    return {
        "chat_response": formatted,
        "function_type": "past_summary",
    }

def _format_summary_markdown(s: dict) -> str:
    """summary_dict → 프론트엔드 표시용 마크다운 문자열 변환."""
    lines = []

    # 이전 회의 종합 요약이면 회의 목록 먼저 표시
    meetings = s.get("meetings", [])
    if meetings:
        lines.append("## 📋 이전 회의 종합 요약")
        for m in meetings:
            lines.append(f"- **{m.get('title', '')}** ({m.get('date', '')})")
    else:
        # 현재 회의 요약 (기존 방식)
        overview = s.get("overview", {})
        purpose = overview.get("purpose") or "회의 요약"
        lines.append(f"## 📋 {purpose}")
        if overview.get("datetime_str"):
            lines.append(f"**일시:** {overview['datetime_str']}")

    # 참석자 — meetings 없을 때 (현재 회의)만 표시  
    if not meetings:                                                                                     
        attendees = s.get("attendees", [])
        if attendees:                                                                                                        
            lines.append(f"**참석자:** {', '.join(attendees)}")

    discussion = s.get("discussion_items", [])
    if discussion:
        lines.append("\n### 🗂 주요 논의 사항")
        for i, item in enumerate(discussion, 1):
            lines.append(f"\n**{i}. {item.get('topic', '')}**")
            lines.append(item.get("content", ""))

    decisions = s.get("decisions", [])
    if decisions:
        lines.append("\n### ✅ 결정 사항")
        for d in decisions:
            lines.append(f"- {d.get('decision', '')}")

    actions = s.get("action_items", [])
    if actions:
        lines.append("\n### 📌 할 일\n")
        lines.append("| 담당자 | 내용 | 기한 | 긴급도 |")
        lines.append("|---|---|---|---|")
        urgency_label = {"urgent": "🔴 긴급", "normal": "⚠️ 보통", "low": "🟢 낮음"}
        for a in actions:
            assignee = a.get("assignee") or "미정"
            content = a.get("content", "")
            deadline = a.get("deadline") or "-"
            urgency = urgency_label.get(a.get("urgency", "low"), "-")
            lines.append(f"| {assignee} | {content} | {deadline} | {urgency} |")

    pending = s.get("pending_items", [])
    if pending:
        lines.append("\n### 🔁 미결 사항")
        for p in pending:
            suffix = " _(이전 회의 연속)_" if p.get("carried_over") else ""
            lines.append(f"- {p.get('content', '')}{suffix}")

    followups = s.get("previous_followups", [])
    if followups:
        lines.append("\n### 🔄 이전 회의 follow-up")
        for f in followups:
            status = "✅ 완료" if f.get("completed") else "⏳ 미완료"
            lines.append(f"- {f.get('previous_action', '')} — {status}")

    if s.get("next_meeting"):
        lines.append(f"\n**다음 회의:** {s['next_meeting']}")

    return "\n".join(lines)

async def classify_intent(state: SharedState) -> dict:
    """summary 여부만 판단 - 나머지는 전부 knowledge_node로"""
    prompt = f"""
    사용자 입력이 "현재 진행 중인 회의 전체 내용을 요약해달라"는 요청인지 판단하세요. 단어 하나만 출력하세요.
                                                                                                                         
    - summary: 현재 회의 내용 요약/정리 요청. 예) "오늘 회의 요약해줘", "지금까지 논의 정리해줘", "중간 정리해줘"
    - past_summary: 이전/지난 회의 내용을 요약해달라는 요청. 예) "이전 회의 요약해줘", "지난 회의 정리해줘", "전 회의 내용 요약"      
    - agent: 특정 문서/자료 검색, 외부 정보 조회, 일정 관련, 특정 주제에 대한 질문 등 그 외 모든 입력.                 
            예) "AI 브리프 내용 요약해줘", "지난 회의에서 결정된 거 알려줘", "~~문서 찾아줘"                         
                                                                                                                        
    입력: {state['user_question']} 
    """
    result = await llm.ainvoke(prompt)
    function_type = result.content.strip().lower()                                                                     
    # LLM이 예상 밖의 값을 반환하면 agent로 fallback
    if function_type not in ("summary", "past_summary", "agent"):                                                                      
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
        metadata={"workspace_id": workspace_id}
    )