import json
import re
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, MessagesState, END
from pymongo import MongoClient
import chromadb
import redis

from app.core.config import settings
from app.core.graph.state import SharedState
from app.utils.redis_utils import get_meeting_context

# --- 클라이언트 초기화 ---
# 모듈 로드 시 한 번만 연결. 요청마다 새로 연결하지 않음.
mongo_db = MongoClient(settings.MONGODB_URL)["workb"]
chroma_client = chromadb.HttpClient(
    host=settings.CHROMA_HOST,
    port=settings.CHROMA_PORT,
)
r = redis.from_url(settings.REDIS_URL)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.OPENAI_API_KEY
)

# --- 도구 정의 ---
# react_agent에 bind되어 LLM이 필요에 따라 호출함.
# @tool 데코레이터가 함수 시그니처와 docstring을 LLM용 tool_schema로 변환함.

@tool
def search_past_meetings(query: str) -> list:
    """이전 회의 내용에서 관련 정보를 검색한다."""
    try:
        # $meta 연산자를 사용하여 텍스트 검색 결과를 점수 순으로 정렬
        cursor = mongo_db["meeting_contexts"].find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}}, # 점수를 'score' 필드에 저장
        ).sort([("score", {"$meta": "textScore"})]).limit(5) # 점수 순으로 정렬

        return [
            {
                "source": "past_meetings",
                "title": doc.get("title", "이전 회의"),
                "snippet": doc.get("summary", ""),
                "url": None,
                "relevance_score": doc.get("score", 0.5)
            }
            for doc in cursor
        ]
    except Exception:
        return []

@tool
def search_internal_db(query: str) -> list:
    """회사 내부 문서에서 관련 정보를 시멘틱 검색한다."""
    try:
        collection = chroma_client.get_or_create_collection("internal_docs")
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

def knowledge_node(state: SharedState) -> dict:
    """
    사용자 질문을 react_agent로 처리하는 메인 Q&A 노드.

    system_prompt에 현재 회의 발화 전체를 컨텍스트로 주입해
    LLM이 회의 내용을 기반으로 답변하거나 필요한 도구를 선택하게 한다.
    """
    meeting_context = get_meeting_context(state["meeting_id"])

    system_prompt = f"""
    당신은 회의 AI 어시스턴트입니다.

    현재 회의 발화 내용:
    {meeting_context}
    
    규칙:
    - 회의 발화 데이터는 최대 약 30초 전까지의 내용만 반영됩니다. 가장 최근 발화는 포함되지 않을 수 있음을 답변에 명시하세요.
    - 회의 내용만으로 답할 수 있으면 도구 없이 답변하세요.
    - 정보가 불완전하더라도 회의에서 언급된 내용을 바탕으로 최대한 답변하세요.
    - 확실하지 않은 정보는 "~라고 언급됐습니다" 형식으로 답변하세요.
    - 외부 자료가 필요하면 web_search를 사용하세요.
    - 이전 회의 내용이 필요하면 search_past_meetings를 사용하세요.
    - 회사 내부 문서가 필요하면 search_internal_db를 사용하세요.
    - 일정 등록 요청이면 register_calendar를 사용하세요.
    - 일정 수정 요청이면 update_calendar_event를 사용하세요.
    - 일정 삭제 요청이면 delete_calendar_event를 사용하세요.
    - 특정 날짜나 일정에 대해 물어보면 get_calendar_events를 사용하세요.
    """

    result = react_agent.invoke({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["user_question"]}
        ]
    })

    return {
        "chat_response": result["messages"][-1].content,
        "function_type": "agent"
    }

def summary_node(state: SharedState) -> dict:
    """
    회의 발화 전체를 구조화된 JSON 요약으로 변환하는 노드.

    흐름:
        1. 컨텍스트 로드 - partial_summary 캐시 우선, 없으면 전체 발화
        2. 이전 회의 데이터 조회 - follow-up 추적에 사용
        3. 프롬프트 구성 - agenda 유무에 따라 분기
        4. LLM 호출 - SummaryResponse 구조 강제
        5. 할루시네이션 검증 - 발화 키워드 겹침률로 신뢰도 판정
    """

    meeting_id = state["meeting_id"]

    # 1단계: 컨텍스트 로드
    # partial_summary가 있으면 이미 요약된 앞부분은 재처리하지 않고 재사용.
    # 없으면 Redis에서 전체 발화를 가져온다.
    cached = r.get(f"meeting:{meeting_id}:partial_summary")
    if cached:
        # 이전 partial_summary + 새 발화만 이어붙여 중분 처리
        prev_summary = cached.decode()
        new_utterances = get_meeting_context(meeting_id)
        context = f"[이전 요약]\n(prev_summary)\n\n[추가 발화]\n{new_utterances}"
    else:
        context = get_meeting_context(meeting_id)

    # 2단계: 이전 회의 데이터 조회
    # 발화 앞부분 200자를 쿼리로 사용해 관련 이전 회의를 검색
    # search_past_meetings는 @tool이므로 .invoke()로 직접 호출.
    past_meetings = search_past_meetings.invoke({"query": context[:200]})
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

    반드시 아래 JSON 형식으로만 답변하세요. 내용이 없는 섹션은 [] 또는 null. "없음" 텍스트 사용 금지.

    {{
        "overview": {{"purpose": "...", "datetime_str": "..."}},
        "discussion_items": [{{"topic": "...", "content": "..."}}],
        "decisions": [{{"decision": "...", "rationale": "...", "opposing_opinion": "..."}}],
        "action_items": [{{"assignee": "...", "content": "...", "deadline": "...", "priority": "high|normal", "urgency": "urgent|normal|low"}}],
        "pending_items": [{{"content": "...", "carried_over": false, "first_mentioned_meeting": null}}],
        "next_meeting": "...",
        "previous_followups": [{{"previous_action": "...", "completed": false}}],
        "hallucination_flags": []
    }}
    """

    # 4단계: LLM 호출
    result = llm.invoke(prompt)
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
        d.get("decision", "") for d in summary_dict.get("decisions", [])
    ] + [
        a.get("content", "") for a in summary_dict.get("action_items", [])
    ]

    for item_text in check_targets:
        if not item_text:
            continue
        item_words = set(re.findall(r"[가-힣a-zA-Z0-9]+", item_text))
        # 겹치는 단어 수 / 요약 항목 단어 수
        overlap = len(item_words & context_words) / len(item_words) if item_words else 0
        flags.append({
            "item": item_text,
            "confidence": "verified" if overlap >= 0.4 else "needs_review"
        })

    summary_dict["hallucination_flags"] = flags

    # partial_summary 캐시 갱신
    # 다음 요약 호출 시 이미 처리한 내용을 재처리하지 않기 위해 저장.
    # TTL 3600초(1시간) — 회의 종료 후 자동 만료.
    try:
        overview = summary_dict.get("overview", {})
        partial_text = overview.get("purpose", "") or json.dumps(
            summary_dict.get("discussion_items", [])[:2], ensure_ascii=False
        )
        r.set(f"meeting:{meeting_id}:partial_summary", partial_text, ex=3600)
    except Exception:
        pass  # 캐시 저장 실패는 요약 결과에 영향 없음

    return {
        "summary": summary_dict,
        "chat_response": _format_summary_markdown(summary_dict),
        "function_type": "summary"
    }

def _format_summary_markdown(s: dict) -> str:
    """summary_dict → 프론트엔드 표시용 마크다운 문자열 변환."""
    lines = []

    overview = s.get("overview", {})
    purpose = overview.get("purpose") or "회의 요약"
    lines.append(f"## 📋 {purpose}")
    if overview.get("datetime_str"):
        lines.append(f"**일시:** {overview['datetime_str']}")

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
            if d.get("rationale"):
                lines.append(f"  - 근거: {d['rationale']}")
            if d.get("opposing_opinion"):
                lines.append(f"  - 반대 의견: {d['opposing_opinion']}")

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

def classify_intent(state: SharedState) -> dict:
    """summary 여부만 판단 - 나머지는 전부 knowledge_node로"""
    prompt = f"""
    사용자 입력이 회의 내용 요약 요청인지 판단하세요. 단어 하나만 출력하세요

    - summary: 요약해줘, 정리해줘, 중간 정리 등 명시적 요약 요청
    - agent: 그 외 모든 입력

    입력: {state['user_question']}
    """
    result = llm.invoke(prompt)
    return {"function_type": result.content.strip()}