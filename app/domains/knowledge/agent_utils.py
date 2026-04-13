# app\domains\knowledge\agent_utils.py
import redis
import json
import os

from app.core.config import settings
from langchain_openai import ChatOpenAI
from app.core.graph.state import SharedState

llm = ChatOpenAI(model="gpt-4o", api_key=settings.OPENAI_API_KEY)
r = redis.from_url(settings.REDIS_URL)

# redis reader 함수
def get_meeting_context(meeting_id: str) -> str:
    # 발화 전체 읽기
    utterances_raw = r.lrange(f"meeting:{meeting_id}:utterances", 0, -1)

    # 화자 이름 매핑
    # {speaker_id: speaker_name}, hgetall: hash 형태로 데이터 읽기
    speakers = r.hgetall(f"meeting:{meeting_id}:speakers")
    speakers = {k.decode(): v.decode() for k, v in speakers.items()}

    # 컨텍스트 문자열 조합
    lines = []
    for u in utterances_raw:
        # json.loads: string -> dict, loads(): json 문자열을 파이썬 객체로 변환
        utterance = json.loads(u)
        name = speakers.get(utterance['speaker_id'], utterance["speaker_id"])
        lines.append(f"[{name}] {utterance['content']}")

    return "\n".join(lines)

# 기능별 프롬프트 템플릿
def build_qa_prompt(context: str, question: str) -> str:
    return f"""
        다음은 현재 진행 중인 회의의 발화 내용입니다.

        {context}

        위 회의 내용을 바탕으로 아래 질문에 답해주세요.
        질문: {question}
    """

def build_summary_prompt(context: str) -> str:
    return f"""
        다음은 현재까지의 회의 발화 내용입니다.

        {context}

        위 내용을 아래 형식으로 요약해주세요.
        - 주요 논의 사항
        - 결정된 사항
        - 미결 사항
    """

def intent_classifier(state: SharedState) -> dict:
    # 사용자 입력 분석 -> function_type 결정
    prompt = f"""
        사사용자 입력을 분석해서 아래 중 하나로만 답하세요. 단어 하나만 출력하세요.
        
        - chat: 회의 내용에 대한 질문, 확인, 조회
        - summary: 요약 요청 (요약해줘, 정리해줘, 중간 정리 등)
        - search: 외부 자료 검색 요청 (찾아줘, 검색해줘, 자료 등)
        - db_query: 회사 내부 문서 조회 요청
        - report: 보고서 생성 요청
        - calendar: 새로운 일정 등록 요청 (캘린더에 추가해줘, 일정 잡아줘 등)

        주의: 회의에서 언급된 일정을 묻는 질문은 chat입니다.
        예시: "기한이 언제야?", "몇 시라고 했어?" → chat
        
        입력: {state['user_question']}    
    """

    result = llm.invoke(prompt)
    return {"function_type": result.content.strip()}

def chat_node(state: SharedState) -> dict:
    context = get_meeting_context(state['meeting_id'])
    prompt = build_qa_prompt(context, state['user_question'])
    result = llm.invoke(prompt)
    return {"chat_response": result.content}

def summary_node(state: SharedState) -> dict:
    context = get_meeting_context(state['meeting_id'])
    prompt = build_summary_prompt(context)
    result = llm.invoke(prompt)
    return {"chat_response": result.content}

# 나머지는 placeholder
def search_node(state): return {"chat_response": "search 미구현"}
def db_query_node(state): return {"chat_response": "db_query 미구현"}
def report_node(state): return {"chat_response": "report 미구현"}
def calendar_node(state): return {"chat_response": "calendar 미구현"}