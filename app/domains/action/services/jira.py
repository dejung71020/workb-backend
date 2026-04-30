# app/domains/action/services/jira.py
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app.domains.action import repository
from app.domains.integration import repository as integration_repo
from app.domains.integration.models import ServiceType
from app.domains.integration.service import get_valid_jira_token, get_jira_cloud_id
from app.infra.clients.jira import JiraClient
from app.utils.time_utils import now_kst

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "urgent":   "Highest",
    "critical": "Highest",
    "high":     "High",
    "medium":   "Medium",
    "low":      "Low",
}
async def export_jira(
        db: Session,
        workspace_id: int,
        meeting_id: int,
) -> dict:
    '''
    웹 서비스 WBS를 JIRA로 내보내는 함수
    '''
    token = await get_valid_jira_token(db, workspace_id)
    cloud_id = get_jira_cloud_id(db, workspace_id)
    integration = integration_repo.get_integration(db, workspace_id, ServiceType.jira)
    project_key = (integration.extra_config or {}).get("project_key")
    if not project_key:
        raise ValueError("JIRA 프로젝트가 선택되지 않았습니다. 다시 시도하세요.")
    
    client = JiraClient(token, cloud_id)
    epics = repository.get_wbs_epics(db, meeting_id)

    created, updated, failed = 0, 0, []
    for epic in epics:
        try:
            # 처음 내보내는 에픽 일 때 (신규 생성 에픽)
            if not epic.jira_epic_id:
                epic_key = await client.create_epic(project_key, epic.title)
                repository.update_epic_jira_id(db, epic.id, epic_key)
                epic.jira_epic_id = epic_key
                created += 1
            
            # 이미 내보낸 에픽일 때 제목만 업데이트
            else:
                await client.update_issue(epic.jira_epic_id, {"summary": epic.title})
                updated += 1
        
        except Exception as e:
            logger.error(f"Epic 처리 실패 epic_id={epic.id}: {e}")
            failed.append(f"Epic: {epic.title}")
            continue

        # epic에 속한 task 다 불러옴
        tasks = repository.get_wbs_tasks_by_epic(db, epic.id)
        for task in tasks:
            try:
                # 우선순위 매핑
                priority = _PRIORITY_MAP.get(
                    task.priority.value if hasattr(task.priority, 'value') else task.priority,
                    "Medium"
                )
                # 마감일 문자열 처리
                due_date = str(task.due_date) if task.due_date else None

                # 담당자 accountId 조회
                assignee_id = None
                if task.assignee_name:
                    try:
                        users = await client.search_user(task.assignee_name)
                        if users:
                            assignee_id = users[0].get("accountId")
                    except Exception:
                        pass

                # 처음 내보내는 태스크 일 때 (신규 생성 태스크)
                if not task.jira_issue_id:
                    issue_key = await client.create_issue(
                        project_key=project_key,
                        summary=task.title,
                        epic_key=epic.jira_epic_id,
                        priority=priority,
                        due_date=due_date,
                        assignee_account_id=assignee_id,
                    )
                    repository.update_task_jira_id(db, task.id, issue_key)
                    created += 1
                
                # 이미 있는 태스크 일 때 (기존 값만 업데이트)
                else:
                    fields = {
                        "summary": task.title,
                        'priority': {
                            "name": priority
                        }
                    }
                    if due_date:
                        fields['duedate'] = due_date
                    if assignee_id:
                        fields['assignee'] = {"accountId": assignee_id}
                    await client.update_issue(task.jira_issue_id, fields)
                    updated += 1
            except Exception as e:
                logger.error(f"Task 처리 실패 task_id={task.id}: {e}")
                failed.append(f"Task: {task.title}")
    return {
        "created": created,
        "updated": updated,
        "failed": failed
    }

async def sync_from_jira(
        db: Session,
        workspace_id: int,
        meeting_id: int,
) -> dict:
    # 1단계: JIRA에 등록된 태스크만 골라내기
    token = await get_valid_jira_token(db, workspace_id)
    cloud_id = get_jira_cloud_id(db, workspace_id)
    integration = integration_repo.get_integration(db, workspace_id, ServiceType.jira)
    status_maaping: dict = (integration.extra_config or {}).get("status_mapping", {})

    # jira_issue_id 있는 태스크만 수집
    epics = repository.get_wbs_epics(db, meeting_id)
    tasks_with_jira = []
    for epic in epics:
        for task in repository.get_wbs_tasks_by_epic(db, epic.id):
            if task.jira_issue_id:
                tasks_with_jira.append(task)
    
    if not tasks_with_jira:
        return {
            "changed": [],
            "unchanged": 0,
            "synced_at": now_kst().isoformat()
        }
    
    client = JiraClient(token, cloud_id)

    # 2단계: JQL로 한 번에 조회하기
    # N + 1 방지 : JQL 배치 조회
    keys = [t.jira_issue_id for t in tasks_with_jira]
    jql = f"issueKey in ({', '.join(keys)})"
    
    # 1번의 API 호출로 모든 정보를 가져옴
    issues = await client.search_by_jql(jql, fields="status,summary")

    # key -> issue 딕셔너리
    issue_map = {issue['key']: issue for issue in issues}

    changed = []
    unchanged = 0

    # 3단계: 변경된 내용 비교 & DB 업데이트
    for task in tasks_with_jira:
        issue = issue_map.get(task.jira_issue_id)
        if not issue:
            continue
        
        # Status 비교
        jira_status_name = issue.get("fields", {}).get("status", {}).get("name", "")
        jira_title = issue.get("fields", {}).get("summary", "")
        workb_status = status_maaping.get(jira_status_name, "todo")
        current_status = task.status.value if hasattr(task.status, "value") else task.status

        task_changed = False

        if workb_status != current_status:
            changed.append({
                "task_id": task.id,
                "jira_key": task.jira_issue_id,
                "field": "status",
                "old": current_status,
                "new": workb_status,
            })
            repository.update_wbs_task(db, task.id, status=workb_status)
            task_changed = True

        if jira_title and jira_title != task.title:
            changed.append({
                "task_id": task.id,
                "jira_key": task.jira_issue_id,
                "field": "title",
                "old": task.title,
                "new": jira_title,
            })
            repository.update_wbs_task(db, task.id, title=jira_title)
            task_changed = True

        if not task_changed:
            unchanged += 1

    return {
        "changed": changed,
        "unchanged": unchanged,
        "synced_at": now_kst().isoformat(),
    }

