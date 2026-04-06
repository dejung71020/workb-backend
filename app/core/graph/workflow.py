# app\core\graph\workflow.py

from langgraph.graph import StateGraph, END
from app.core.graph.state import SharedState
from app.core.graph.supervisor import supervisor_node

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