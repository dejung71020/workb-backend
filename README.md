---
# 📑 [가이드라인] 백엔드 도메인 개발 표준 규격 (v1.1)

이 가이드는 **BACKEND** 프로젝트의 일관성을 유지하고, 멀티 에이전트 시스템의 원활한 오케스트레이션을 위해 모든 도메인 개발자가 반드시 준수해야 할 표준입니다.
---

## 1. 폴더 구조 및 역할 (Layered Architecture)

각 도메인은 `app/domains/{domain_name}/` 폴더 내에 아래 6개 파일을 기본으로 구성합니다.

| 파일명           | 역할                       | 비고                                       |
| :--------------- | :------------------------- | :----------------------------------------- |
| `agent_utils.py` | **Prompt store**           | LLM Prompt를 정의                          |
| `models.py`      | **Database Entity**        | SQLAlchemy를 이용한 DB 테이블 정의         |
| `schemas.py`     | **Data Contract (DTO)**    | Pydantic을 이용한 입출력 규격 정의         |
| `repository.py`  | **Data Access (Hand)**     | 순수 DB CRUD 로직 (비즈니스 로직 금지)     |
| `service.py`     | **Business Logic (Brain)** | 에이전트 호출, 데이터 가공, 타 도메인 협업 |
| `router.py`      | **API Endpoint (Door)**    | 외부 요청 수신 및 서비스 연결              |

---

## 2. 레이어별 코드 템플릿

### 📂 models.py (데이터의 뼈대)

```python
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.infra.database.base import Base
from datetime import datetime

class DomainModel(Base):
    __tablename__ = "domain_table_name"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 📂 schemas.py (데이터 통신 규격)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class DomainBase(BaseModel):
    title: str

class DomainCreate(DomainBase):
    pass

# 출력은 이런식으로 Response를 클래스이름 뒤에 붙여주세요.
# 입력은 Request를 클래스이름 뒤에 붙여주세요.
class DomainResponse(DomainBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
```

### 📂 repository.py (데이터 저장/조회)

```python
from sqlalchemy.orm import Session
from . import models, schemas

class DomainRepository:
    @staticmethod
    def save_data(db: Session, data: schemas.DomainCreate):
        db_obj = models.DomainModel(**data.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    @staticmethod
    def get_by_id(db: Session, obj_id: int):
        return db.query(models.DomainModel).filter(models.DomainModel.id == obj_id).first()
```

### 📂 service.py (핵심 에이전트 로직)

> **중요:** 에이전트 노드로 활용될 함수는 반드시 `state: SharedState`를 인자로 받고 업데이트된 `dict`를 반환해야 합니다.

```python
from sqlalchemy.orm import Session
from .repository import DomainRepository
from app.core.graph.state import SharedState

class DomainService:
    @staticmethod
    async def process_agent_task(state: SharedState, db: Session) -> dict:
        """
        LangGraph Node로 등록될 비즈니스 로직
        """
        # 1. State에서 데이터 읽기
        current_context = state.get("transcript", "")

        # 2. 에이전트(LLM) 실행 (예시)
        # result = await llm_call(current_context)

        # 3. DB 저장 필요 시 Repository 사용
        # DomainRepository.save_data(db, ...)

        # 4. 업데이트할 State 조각 반환
        return {"summary": "분석된 요약 결과"}
```

### 📂 router.py (API 입구)

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.infra.database.session import get_db
from . import service, schemas

router = APIRouter(prefix="/domain-path", tags=["DomainTag"])

@router.post("/", response_model=schemas.DomainResponse)
async def create_endpoint(data: schemas.DomainCreate, db: Session = Depends(get_db)):
    return await service.DomainService.handle_api_request(data, db)
```

---

## 3. 🤝 협업 핵심 규칙

### 💡 Shared State 활용 규칙 (`app/core/graph/state.py`)

- 모든 도메인 서비스는 중앙 `SharedState`에 정의된 키(Key)만 사용합니다.
- **Write Rule:** 자신이 담당한 도메인의 키만 수정합니다. 타 도메인의 데이터는 **Read-only**로 취급합니다.

### 💡 에이전트 순환(Loop) 처리

- `service.py`에서 작업 결과가 불충분하다고 판단될 경우, `SharedState`에 에러 메시지나 재시도 플래그를 담아 반환합니다.
- 예: `return {"errors": ["데이터 부족"], "next_step": "researcher"}`

### 💡 비동기(Async) 원칙

- LLM 호출 및 외부 API(Jira, Slack) 연동은 반드시 `async/await`를 사용하여 시스템 전체의 병목을 방지합니다.

---

## 4. 작업 실패 및 로그 (QA/Ops 관점)

- 모든 `service.py` 내 에이전트 호출 구간에는 `try-except` 블록을 구성하고, 에러 발생 시 `QA/Ops` 도메인이 추적할 수 있도록 `state["errors"]`에 로그를 남깁니다.

---

## 5. Github 통일 예시

- 6명이 동시에 코드를 밀면 충돌이 잦습니다. 도메인별 영역을 확실히 나누는 규칙이 필요합니다.
  Branch: feature/meeting, feature/action, feature/core 등 도메인별 브랜치 사용.

Commit Message: feat(meeting): add speaker diarization logic 처럼 접두어를 붙여 누가 어느 도메인을 건드렸는지 명시.

---

## 6. .env 명시

- 모든 도메인이 공통으로 쓰는 API Key와 DB 접속 정보 리스트를 README에 명시해야 합니다.

예: OPENAI_API_KEY, TAVILY_API_KEY, JIRA_API_TOKEN, DATABASE_URL 등.

.env.example 파일을 만들어 실제 키 값만 빠진 템플릿을 공유하세요.

---

## 7. 에이전트 프롬프트 관리 규칙

- 프롬프트가 코드 여기저기에 흩어지는 경우를 예방
  규칙: 모든 프롬프트는 각 도메인의 agent_utils.py 파일로 관리하고, 버전 번호를 매길 것.

---

## 8. 실행 방법, 테스트 방법

### 🚀 [초기 세팅 방법]

#### 1. 가상환경 생성 및 활성화

```bash
python -m venv venv

# Mac / Linux
source venv/bin/activate

# Windows
source venv/Scripts/activate
```

---

#### 2. 패키지 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt

# 오류나면 아래로 해봐요
PYTHONUTF8=1 pip install -r requirements.txt
```

---

#### 3. 환경 변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성한 뒤,
본인의 API Key 및 설정 값을 입력합니다.

```bash
cp .env.example .env  # Mac / Linux
copy .env.example .env  # Windows
```

---

## 🧪 테스트 방법

---

### 1. 서버 실행

```bash
uvicorn app.main:app --reload
```

---

### 2. API 테스트 (Swagger UI)

브라우저에서 접속:

```
http://localhost:8000/docs
```

👉 FastAPI 기본 Swagger UI에서 API를 직접 테스트할 수 있습니다.

---

### 3. 유닛 테스트 실행

```bash
pytest
```

---

### 4. 특정 도메인 테스트 실행

```bash
pytest tests/domains/meeting
```

---

### 🔥 실행 흐름 요약

```
환경 세팅 → 서버 실행 → Swagger 테스트 → pytest 검증
```

---

### 💡 실무 팁

- `.env`는 절대 Git에 올리지 말 것 (`.gitignore` 필수)
- `pre-commit` 설정하면 팀 코드 스타일 통일됨
- 테스트 먼저 작성하면 유지보수 난이도 ↓

---

## 📊 도메인별 업무 분담표 (R&R)

각 담당자는 본인 도메인 폴더(`app/domains/{domain}/`) 내의 로직을 책임지며,
**SharedState에서 본인 영역의 Key만 업데이트**합니다.
| 도메인 | 핵심 기능 및 웹 서비스 역할 | 관리 데이터 (SharedState Key) | 사용 DB |
|--------|----------------------------|------------------------------|--------|
| Integration (System) | [온보딩/설정] 워크스페이스/회의 고유 식별자 관리 및 외부 서비스(Jira 등) OAuth 연동 정보 보유. | workspace_id, meeting_id, next_node, current_scenario | PostgreSQL |
| User | [인증] 회원가입, 로그인, 음성 지문(Voice Fingerprint) 등록 및 화자 분리용 프로필 관리. | user_id (세션 관리용) | PostgreSQL |
| Workspace | [팀 관리] 워크스페이스 멤버 권한 및 팀별 맞춤 설정 관리. | workspace_id | PostgreSQL |
| Meeting (Scribe) | [회의 중] 실시간 STT 및 화자 분리 발화 스트림 생성. | transcript | Redis, PostgreSQL |
| Knowledge (Researcher) | [검색] 즉석 자료 검색 및 과거 회의록 RAG 검색. 사용자별 개별 질문 답변 생성. | search_query, retrieved_docs, chat_history, user_question, chat_response | Pinecone |
| Intelligence (Analyst) | [분석/제어] 요약본 및 결정사항 도출. 전체 그래프 흐름(Supervisor) 순서 및 분기 계산. | summary, decisions, previous_context | PostgreSQL |
| Vision (Interpreter) | [비전 분석] 공유 화면/이미지 OCR 및 발표 맥락 해석 결과 제공. | screenshot_analysis | PostgreSQL, S3 |
| Action (Architect) | [실행/변환] 실시간 액션 아이템 감지, WBS 생성. 문서(Excel, PDF 등) 변환 및 다운로드 링크 생성. | wbs, realtime_actions, external_links | PostgreSQL, S3 |
| Quality (QA/Ops) | [품질/모니터링] 결과물 정확도 검증 및 전체 프로세스 에러/지연 모니터링. | integration_settings, accuracy_score, errors | PostgreSQL |

---

1. State 파일 최종 확인: app/core/graph/state.py에 위에서 정의한 모든 키가 누락 없이 포함되어 있는지 확인합니다.

2. Supervisor 라우팅 로직: app/core/graph/supervisor.py에서 next_node와 current_scenario를 활용해 각 시나리오별로 에이전트들을 적절히 호출하도록 로직을 구성합니다.

3. 노드 등록: app/core/graph/workflow.py에 각 도메인의 서비스 함수를 노드로 등록하고, SharedState를 통해 데이터를 주고받도록 연결합니다.

---

## 2. 🤝 협업을 위한 3대 원칙 (Collaboration Framework)

팀원들이 각자 개발하면서도 전체 시스템이 하나로 동작하도록 만드는 핵심 규칙입니다.

---

### 1️⃣ 상태 중심 개발 (State-First), 도메인 API 라우터 연결

- 모든 `service.py`는 **SharedState를 입력으로 받는다**
- 반환은 반드시 **수정된 필드만 dict 형태로 반환**

```python
# 예시
def analyst_service(state):
    return {
        "summary": "...",
        "decisions": ["..."]
    }
```

- 각 팀원이 router.py를 완성하면, 이를 중앙에서 합쳐야 합니다. app/api/v1/api_router.py를 다음과 같이 구성하여 팀원들에게 공지하세요.

```python
# app/api/v1/api_router.py
from fastapi import APIRouter
from app.domains.meeting.router import router as meeting_router
from app.domains.knowledge.router import router as knowledge_router
# ... 나머지 도메인 import

api_router = APIRouter()
api_router.include_router(meeting_router)
api_router.include_router(knowledge_router)
# ... 추가 연결
```

- ❗ 타 도메인의 데이터는 **읽기(Read-only)**만 가능

---

### 2️⃣ 모크 우선 방식 (Mock-First)

- 타 도메인 구현을 기다리지 않기 위한 전략
- `tests/mocks/`에 시나리오별 JSON 데이터 정의

```json
{
  "retrieved_docs": [
    {
      "title": "A회의록",
      "content": "예산 결의 완료..."
    }
  ]
}
```

👉 모든 도메인은 이 Mock 데이터를 기준으로 개발 가능

---

### 3️⃣ 독립적 테스트 (Independent Testing)

- 각 도메인은 **자기 입력 → 출력**만 검증
- 전체 시스템 없이도 테스트 가능해야 함

```python
def test_analyst():
    input_state = {
        "retrieved_docs": [{"content": "예산 결의 완료"}]
    }

    result = analyst_service(input_state)

    assert "summary" in result
```

---

## 🚀 핵심 구조 요약

```text
각 도메인은 독립적으로 개발한다
→ SharedState를 통해 연결된다
→ Supervisor가 전체 흐름을 제어한다
```

---

## 🔥 한 줄 핵심

> "도메인은 자기 Key만 책임지고, SharedState로 협력한다"

| 담당자                 | 담당 영역 (도메인 폴더 및 로직)                 | 핵심 미션                                                                                           |
| ---------------------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 인원 1 (PM/Architect)  | System(Supervisor 로직) + User + Workspace 중간 | 전체 흐름 설계자. supervisor.py의 판단 로직을 짜고, 회원가입/팀 생성 등 서비스의 입구를 만듭니다.   |
| 인원 2 (Audio AI)      | Meeting (Scribe) 중간                           | 데이터 공급자. STT 엔진을 연결하고 실시간 발화 데이터를 Redis와 DB에 안정적으로 쌓는 역할을 합니다. |
| 인원 3 (Search/RAG)    | Knowledge (Researcher) 쉬움                     | 정보 검색가. Pinecone 연동 및 RAG 로직을 구축하여 에이전트가 과거 기록을 정확히 찾아오게 합니다.    |
| 인원 4 (NLP/Analyst)   | Intelligence (Analyst) 쉬움                     | 분석가. 요약, 결정사항 추출 등 핵심 LLM 프롬프트를 설계하고 분석 결과의 품질을 책임집니다.          |
| 인원 5 (Action/DevOps) | Action (Architect) + Integration 어려움         | 해결사. WBS 생성, 엑셀/PDF 변환, Jira/Slack API 연동 및 실제 파일 다운로드 시스템을 구축합니다.     |
| 인원 6 (Vision/QA)     | Vision (Interpreter) + Quality (QA/Ops) 중간    | 감시자. 화면 OCR 분석과 함께 시스템 전체의 에러 모니터링, 결과물 정확도 검증 로직을 담당합니다.     |
