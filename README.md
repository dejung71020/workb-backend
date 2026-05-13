# 🤝 WorkB — 회의 에이전트 웹서비스

> 회의 내용의 통일성 확보, 결정사안의 반자동 처리를 목표로 한 멀티 외부 서비스 통합 웹서비스

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-4479A1?style=flat-square&logo=mysql&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat-square&logo=mongodb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat-square&logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![nginx](https://img.shields.io/badge/nginx-009639?style=flat-square&logo=nginx&logoColor=white)

---

## 📌 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 기간 | 2026.04 – 2026.05 |
| 팀 구성 | 6명 |
| 담당 | 백엔드 개발 · 외부서비스 연동 · 배포 |
| 아키텍처 | Domain-Driven Design (DDD) |

### 기존 회의의 문제
- 할 일 메모하며 회의 → 집중도 하락
- 결정사안을 각자 다르게 이해 → 대화 왜곡
- Jira 수동 할당, Slack 지시, 다음 일정 개별 질의 → 외부 서비스 파편화

### 해결 파이프라인
```
화자분리 · 내용저장 → 회의 요약 · 태스크 분해 → 사용자 확인 및 편집
→ 원클릭 내보내기 (Jira + Slack + Calendar) → 다음 회의 일정 추천
```

---

## 🛠 기술 스택

| 분류 | 기술 |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic |
| Database | MySQL (19개 테이블), MongoDB, Redis, ChromaDB |
| Infra | Docker Compose, nginx (Self-signed HTTPS) |
| Auth | JWT (Access/Refresh Token), OAuth 2.0 |
| External | Slack, Jira, Google Calendar, Notion, Kakao |

---

## ✨ 핵심 구현

### 1. 외부 서비스 통합 아키텍처 전환 (n8n → FastAPI)

초기에 n8n에 위임하던 구조를 FastAPI 직접 구현으로 전환했습니다.

**전환 이유:** n8n은 정적 크레덴셜에 최적화 → 워크스페이스마다 다른 토큰 관리 불가

**해결:** `BaseClient` 추상 클래스 설계 후 Slack · Jira · Google Calendar · Notion · Kakao 5개 서비스 상속

```python
class BaseClient:
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        ...

class SlackClient(BaseClient): ...
class JiraClient(BaseClient): ...
class GoogleClient(BaseClient): ...
```

- 토큰 만료 5분 전 자동 갱신
- 워크스페이스 단위 독립적인 토큰 관리
- `extra_config` JSON 컬럼으로 서비스별 필요 데이터 흡수

### 2. Docker 기반 통합 개발 환경

MySQL · MongoDB · Redis · ChromaDB · nginx 5개 컨테이너를 `docker-compose` 하나로 통합

```yaml
# 주요 구성
services:
  workb-backend, workb-nginx, workb-mysql
  workb-mongodb, workb-redis, workb-chromadb
```

- `TZ: Asia/Seoul` 전체 주입 → 로그 · 스케줄링 정합성 확보
- nginx Self-signed 인증 → 로컬 HTTPS 구축 (Slack · Notion OAuth 필수 요건)
- `docker-compose up -d` 한 줄로 팀원 전원 동일 환경

### 3. 다음 회의 일정 추천

Slack 채널 멤버 이메일 → Google Calendar Freebusy API → 빈 구간 계산 → 최대 3개 시간대 추천

---

## 🗄 DB 구조

**MySQL (19개 테이블, 6개 도메인)**

| 도메인 | 테이블 |
|---|---|
| 워크스페이스 | workspaces, departments, workspace_members, invite_codes |
| 사용자 | users, user_device_settings |
| 회의 | meetings, meeting_participants, speaker_profiles |
| 회의록/AI | meeting_minutes, decisions, minute_photos, review_requests |
| 액션/WBS | action_items, wbs_epics, wbs_tasks, wbs_snapshots, reports |
| 연동/알림 | integrations, notifications |

**MongoDB** — chatbot_logs, meeting_contexts, utterances

---

## 🚀 실행 방법

```bash
git clone https://github.com/dejung71020/workb-backend.git
cd workb-backend

# .env 파일 설정 (DATABASE_URL, SECRET_KEY, Slack/Jira/Google 키 등)
cp .env.example .env

# 실행
docker-compose up -d --build
```

API 문서: `http://localhost:8000/docs`

---

## 📁 프로젝트 구조

```
app/
├── core/          # 설정, DB 엔진, JWT, lifespan
├── domains/       # 도메인별 분리 (DDD)
│   ├── workspace/
│   ├── user/
│   ├── meeting/
│   ├── intelligence/   # 회의록 · 결정사안 · 검토
│   ├── action/         # 액션아이템 · WBS · 보고서
│   └── integration/    # 외부 서비스 연동
├── infra/
│   ├── clients/   # BaseClient · Slack · Jira · Google
│   └── database/
└── main.py
```
