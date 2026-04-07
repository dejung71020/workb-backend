import os

BASE_DIR = ""

structure = {
    "app": {
        "main.py": "",
        "api": {
            "v1": {
                "api_router.py": ""
            }
        },
        "core": {
            "config.py": "",
            "security.py": "",
            "graph": {
                "state.py": "",
                "workflow.py": "",
                "supervisor.py": ""
            }
        },
        "domains": {
            "meeting": {},
            "intelligence": {},
            "vision": {},
            "knowledge": {},
            "action": {},
            "quality": {}
        },
        "infra": {
            "clients": {
                "google.py": "", # Google Calendar API 클라이언트
                "jira.py": "",   # JIRA API 클라이언트
                "slack.py": "",  # Slack API 클라이언트
            },
            "websocket": {
                "manager.py": "" # 실시간 회의 스트리밍 관리자
            }
        }
    },
    "tests": {},
    "scripts": {},
    ".env": "",
    "requirements.txt": ""
}

domain_files = [
    "__init__.py",
    "router.py",
    "service.py",
    "repository.py",
    "models.py",
    "schemas.py",
    "agent_utils.py"
]


def write_file(file_path):
    # BACKEND 기준 상대경로 계산
    relative_path = os.path.relpath(file_path, BASE_DIR)

    content = ""
    if file_path.endswith(".py"):
        content = f"# {relative_path}\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def create(path, tree):
    for name, content in tree.items():
        full_path = os.path.join(path, name)

        # 파일
        if isinstance(content, str):
            if not os.path.exists(full_path):
                write_file(full_path)
                print(f"[CREATE FILE] {full_path}")
            else:
                print(f"[SKIP FILE] {full_path}")
        else:
            # 폴더
            if not os.path.exists(full_path):
                os.makedirs(full_path)
                print(f"[CREATE DIR] {full_path}")
            else:
                print(f"[SKIP DIR] {full_path}")

            # domains 특별 처리
            if path.endswith("domains"):
                for domain_name in tree.keys():
                    domain_path = os.path.join(path, domain_name)

                    if not os.path.exists(domain_path):
                        os.makedirs(domain_path)

                    for file in domain_files:
                        file_path = os.path.join(domain_path, file)

                        if not os.path.exists(file_path):
                            write_file(file_path)
                            print(f"[CREATE FILE] {file_path}")
                        else:
                            print(f"[SKIP FILE] {file_path}")
                return

            create(full_path, content)


if __name__ == "__main__":
    create(BASE_DIR, structure)