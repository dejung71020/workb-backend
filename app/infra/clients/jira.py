# app\infra\clients\jira.py
import logging
from typing import Any
from .base import BaseClient

logger = logging.getLogger(__name__)

class JiraClient(BaseClient):
    """
    OAuth 2.0 Token 기반 cloud client
    """
    def __init__(self, access_token: str, cloud_id: str):
        super().__init__(
            base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        
    async def get_projects(self) -> list[dict]:
        '''
        지라의 프로젝트를 가져와서 프론트에서 드롭다운으로 보여줄 함수
        50개씩 페이징하여 프로젝트를 모두 가져오는 API를 사용할것이다.
        '''
        all_projects = []
        start_at = 0
        max_results = 50
        is_last = False

        while not is_last:
            # startAt 으로 다음페이지를 요청.
            data = await self._request(
                "GET", f"/project/search?startAt={start_at}&maxResults={max_results}"
            )

            # 현재 페이지의 프로젝트 목록을 전체 프로젝트에 추가
            values = data.get("values", [])
            all_projects.extend(values)

            # JIRA API가 응답으로 주는 isLast 플래그로 반복 종료
            is_last = data.get("isLast", True)
            start_at += max_results
        
        return all_projects
    
    async def get_project_statuses(self, project_key: str) -> list[str]:
        '''
        project의 status 목록 API 호출
        '''
        data = await self._request("GET", f"/project/{project_key}/statuses")
        statuses: list[str] = []

        # 지라는 이슈 타입을 Epic, Task 별로 묶어서 반환
        for issue_type in data:
            for s in issue_type.get("statuses", []):
                name = s.get("name", "")

                # 중복 제거 (아직 없는 이름만 append)
                if name and name not in statuses:
                    statuses.append(name)

        # ["To Do", "In Progress", "In Review", "Done"] 같은 평탄화된 배열 반환
        return statuses
    
    async def search_user(self, query: str) -> list[dict]:
        """
        accountId로만 유저 정보를 검색하는 함수
        """
        data = await self._request("GET", "/user/search", params={"query": query})
        return data if isinstance(data, list) else []
    
    async def create_epic(self, project_key: str, summary: str) -> str:
        """
        JIRA의 빈 도화지 issue를 만드는 API 호출하는 함수

        쉽게 말하면 나 이슈(도화지)를 만들건데 Epic으로 도장 찍어줘!
        """
        body = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": "Epic"},
            }
        }
        data = await self._request("POST", "/issue", json=body)
        return data["key"]
    
    async def create_issue(
            self,
            project_key: str,
            summary: str,
            epic_key: str,
            priority: str = "Medium",
            due_date: str | None = None,
            assignee_account_id: str | None = None,
    ) -> str:
        '''
        issue 자세히 만드는 함수

        epic_key가 이 이슈(태스크)가 연결될 부모 에픽의 키
        '''
        # Payload 조립
        fields: dict[str, Any] = {
            "project": {
                "key": project_key,
            },
            "summary": summary,
            "issuetype": {
                "name": "Task"
            },
            "parent": {
                "key": epic_key
            },
            "priority": {   # 우선 순위(high, medium, low)
                "name": priority
            }
        }

        # Optional 추가
        if due_date:
            fields['duedate'] = due_date

        if assignee_account_id:
            fields['assignee'] = {
                "accountId": assignee_account_id
            }
        
        # API 호출
        data = await self._request("POST", "/issue", json={"fields": fields})

        # 성공인 경우 key 반환
        return data['key']

    async def update_issue(self, issue_key: str, fields: dict) -> None:
        await self._request("PUT", f"/issue/{issue_key}", json={"fields": fields})

    async def search_by_jql(self, jql: str, fields: str = "status,summary,assignee,priority") -> list[dict]:
        '''
        한 방에 싹 다 가져오는 JQL 사용하는 함수
        '''
        all_issues = []
        start_at = 0
        max_results = 100

        while True:
            # 페이지 넘김
            data = await self._request(
                "GET",
                "/search",
                params={
                    "jql": jql,
                    "fields": fields,
                    "maxResults": max_results,
                    "startAt": start_at
                },
            )

            issues = data.get("issues", [])
            all_issues.extend(issues)

            if len(issues) < max_results:
                break

            start_at += max_results
        return all_issues

 