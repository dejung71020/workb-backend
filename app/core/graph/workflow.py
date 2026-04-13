# app\core\graph\workflow.py

from langgraph.graph import StateGraph, END
from app.core.graph.state import SharedState
from app.core.graph.supervisor import supervisor_node
from app.domains.knowledge.agent_utils import (
    intent_classifier, chat_node, summary_node, 
    search_node, db_query_node, report_node, calendar_node
)

workflow = StateGraph(SharedState)

# 1. 노드 등록 (Placeholder)
workflow.add_node("supervisor", supervisor_node)

workflow.add_node("meeting", lambda state: {"next_node": "supervisor"})
workflow.add_node("knowledge", lambda state: {"next_node": "supervisor"})
workflow.add_node("intelligence", lambda state: {"next_node": "supervisor"})
workflow.add_node("vision", lambda state: {"next_node": "supervisor"})
workflow.add_node("action", lambda state: {"next_node": "supervisor"})
workflow.add_node("quality", lambda state: {"next_node": "supervisor"})

# 2. 시작점
workflow.set_entry_point("supervisor")

# 3. 조건부 라우팅 (Supervisor → 각 도메인)
workflow.add_conditional_edges(
    "supervisor",
    lambda state: state["next_node"],
    {
        "meeting": "meeting",
        "knowledge": "knowledge",
        "intelligence": "intelligence",
        "vision": "vision",
        "action": "action",
        "quality": "quality",
        "end": END,
    }
)

# 4. 모든 노드는 작업 후 Supervisor로 복귀
for node in ["meeting", "knowledge", "intelligence", "vision", "action", "quality"]:
    workflow.add_edge(node, "supervisor")

# 5. 컴파일
app_graph = workflow.compile()

# knowledge 노드를 서브그래프로 교체
knowledge_graph = StateGraph(SharedState)
knowledge_graph.add_node("intent_classifier", intent_classifier)
knowledge_graph.add_node("chat", chat_node)
knowledge_graph.add_node("summary", summary_node)
knowledge_graph.add_node("search", search_node)
knowledge_graph.add_node("db_query", db_query_node)
knowledge_graph.add_node("report", report_node)
knowledge_graph.add_node("calendar", calendar_node)

knowledge_graph.set_entry_point("intent_classifier")
knowledge_graph.add_conditional_edges(
    "intent_classifier",
    # state["function_type"] 값에 따라 해당 노드로 이동
    lambda state: state["function_type"],
    {
        "chat": "chat",
        "summary": "summary",
        "search": "search",
        "db_query": "db_query",
        "report": "report",
        "calendar": "calendar",
    }
)
for node in ["chat", "summary", "search", "db_query", "report", "calendar"]:
    knowledge_graph.add_edge(node, END)

knowledge_app = knowledge_graph.compile()