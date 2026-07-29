from __future__ import annotations

def build_agent_runtime(
    *,
    checkpointer=None,
    lease_guard=None,
    artifact_stager=None,
):
    from .langgraph_v1 import LangGraphV1Runtime

    return LangGraphV1Runtime(
        checkpointer=checkpointer,
        lease_guard=lease_guard,
        artifact_stager=artifact_stager,
    )
