from re import T
import redis, json, os
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import StateGraph, MessagesState, END
from pymongo import MongoClient
import chromadb

from app.core.config import settings
from app.core.graph.state import SharedState

# --- 클라이언트 초기화 ---
r = redis.from_url(settings.REDIS_URL)
mongo_db = MongoClient(settings.MONGODB_URL)["workb"]
chroma_client = chromadb.HttpClient(
    host=settings.CHROMA_HOST,
    port=settings.CHROMA_PORT,
)
# llm = ChatGoogleGenerativeAI(
#     model="models/gemini-2.5-flash-lite", 
#     api_key=settings.GEMINI_API_KEY
# )

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.OPENAI_API_KEY
)

# --- Redis reader ---
def get_meeting_context(meeting_id: str) -> str:
    # 발화 전체 읽기    
    utterances_raw = r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)
    # 화자 정보 읽기
    speakers = {
        k.decode(): v.decode()
        for k, v in r.hgetall(f"meeting:{meeting_id}:speakers").items()
    }

    print(f"[DEBUG] meeting_id: {meeting_id}")
    print(f"[DEBUG] utterances count: {len(utterances_raw)}")
    print(f"[DEBUG] speakers: {speakers}")

    lines = []
    for u in utterances_raw:
        utterance = json.loads(u)
        name = speakers.get(utterance["speaker_id"], utterance["speaker_id"])
        lines.append(f"[{name}] {utterance['content']}")
    context = "\n".join(lines)
    print(f"[DEBUG] context:\n{context}")
    return context

# --- 도구 정의 ---
@tool
def search_past_meetings(query: str) -> list:
    """이전 회의 내용에서 관련 정보를 검색한다."""
    try:
        # $meta 연산자를 사용하여 텍스트 검색 결과를 점수 순으로 정렬
        cursor = mongo_db["meeting_contexts"].find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}}, # 점수를 'score' 필드에 저장
        ).sort([("score", {"$meta": "textScore"})]) # 점수 순으로 정렬

        cursor = cursor.limit(5)

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
    end: str,
    description: str = "",
    location: str = ""
) -> dict:
    """
    Google Calendar에 일정을 등록한다.
    start/end 형식: 2026-04-15T14:00:00:+09:00
    end가 언급되지 않았으면 start 기준 1시간 후로 설정하세요.
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
    """Google Calendar 일정을 조회합니다.
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

# --- LangGraph 노드 ---
def knowledge_node(state: SharedState) -> dict:
    meeting_context = get_meeting_context(state["meeting_id"])

    system_prompt = f"""
    당신은 회의 AI 어시스턴트입니다.

    현재 회의 발화 내용:
    (meeting_context)

    규칙:
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
    - 일정 종료 시간이 언급되지 않았으면 시작 시간 기준 1시간 후로 설정하세요.
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
    context = get_meeting_context(state["meeting_id"])
    prompt = f"""
    다음은 현재까지의 회의 발화 내용입니다.

    {context}

    위 내용을 아래 형식으로 요약해주세요.
    - 주요 논의 사항
    - 결정된 사항
    - 미결 사항
    """
    result = llm.invoke(prompt)
    return {"chat_response": result.content, "function_type": "summary"}

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