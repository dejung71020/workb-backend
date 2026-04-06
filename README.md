---
# 📑 [가이드라인] 백엔드 도메인 개발 표준 규격 (v1.1)

이 가이드는 **BACKEND** 프로젝트의 일관성을 유지하고, 멀티 에이전트 시스템의 원활한 오케스트레이션을 위해 모든 도메인 개발자가 반드시 준수해야 할 표준입니다.
---

## 1. 폴더 구조 및 역할 (Layered Architecture)

각 도메인은 `app/domains/{domain_name}/` 폴더 내에 아래 5개 파일을 기본으로 구성합니다.

| 파일명          | 역할                       | 비고                                       |
| :-------------- | :------------------------- | :----------------------------------------- |
| `models.py`     | **Database Entity**        | SQLAlchemy를 이용한 DB 테이블 정의         |
| `schemas.py`    | **Data Contract (DTO)**    | Pydantic을 이용한 입출력 규격 정의         |
| `repository.py` | **Data Access (Hand)**     | 순수 DB CRUD 로직 (비즈니스 로직 금지)     |
| `service.py`    | **Business Logic (Brain)** | 에이전트 호출, 데이터 가공, 타 도메인 협업 |
| `router.py`     | **API Endpoint (Door)**    | 외부 요청 수신 및 서비스 연결              |

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

## 5. Github 통일

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

---

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
