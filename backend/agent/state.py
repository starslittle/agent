from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from agent.root import SkillRouteResolution


WorkflowName = Literal["chat_v1", "research_v1", "fortune_v1"]


class RootState(TypedDict, total=False):
    """Checkpoint-safe state shared by the root graph and frozen workflows."""

    query: str
    messages: list[dict[str, str]]
    context_package: dict[str, Any]
    requested_workflow: str
    selected_workflow: WorkflowName
    route_target: Literal[
        "chat_v1", "research_v1", "fortune_v1", "confirmation_required"
    ]
    skill_resolution: dict[str, Any]
    agent_name: str
    model_profile: str
    prompt_bundle: str
    allowed_capabilities: list[str]
    max_model_calls: int
    max_tool_calls: int
    deadline_seconds: int
    execution_id: str
    shadow: bool

    answer: str
    artifacts: list[dict[str, Any]]
    citations: Annotated[list[dict[str, Any]], operator.add]
    completion: dict[str, Any]
    metadata: dict[str, Any]
    usage: dict[str, int]

    research_plan: dict[str, Any]
    evidence: Annotated[list[dict[str, Any]], operator.add]
    evidence_grade: dict[str, Any]
    pending_search_queries: list[str]
    attempted_search_queries: Annotated[list[str], operator.add]
    research_round: int
    birth_profile: dict[str, Any]
    missing_fields: list[str]
    tool_results: dict[str, str]
    model_calls: int
    tool_calls: Annotated[int, operator.add]
    search_query: str
    search_index: int


def create_root_state(
    *,
    query: str,
    messages: list[dict[str, str]] | None,
    context_package: dict[str, Any] | None,
    requested_workflow: str,
    resolution: SkillRouteResolution,
    execution_id: str,
    shadow: bool = False,
) -> RootState:
    return {
        "query": query,
        "messages": list(messages or []),
        "context_package": dict(context_package or {}),
        "requested_workflow": requested_workflow,
        "skill_resolution": resolution.model_dump(mode="json"),
        "execution_id": execution_id,
        "shadow": shadow,
        "answer": "",
        "artifacts": [],
        "citations": [],
        "completion": {},
        "metadata": {},
        "usage": {},
        "evidence": [],
        "evidence_grade": {},
        "pending_search_queries": [],
        "attempted_search_queries": [],
        "research_round": 0,
        "missing_fields": [],
        "tool_results": {},
        "model_calls": 0,
        "tool_calls": 0,
    }
