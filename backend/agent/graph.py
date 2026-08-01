from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig

from agent.capabilities import CapabilityExecutor
from agent.context import context_from_config
from agent.events import emit_runtime_event
from agent.models import ModelGateway
from agent.specs import AgentCatalog
from agent.state import RootState
from agent.skills import SkillRegistry, get_skill_registry
from agent.workflows import (
    build_chat_workflow,
    build_fortune_workflow,
    build_research_workflow,
)


def build_root_graph(
    gateway: ModelGateway,
    capability_executor: CapabilityExecutor,
    catalog: AgentCatalog,
    checkpointer=None,
    *,
    skill_registry: SkillRegistry | None = None,
):
    skill_registry = skill_registry or get_skill_registry()
    chat = build_chat_workflow(gateway)
    research = build_research_workflow(gateway, capability_executor)
    fortune = build_fortune_workflow(gateway, capability_executor)

    async def normalize_and_route(state: RootState):
        resolution = state["skill_resolution"]
        spec = catalog.resolve(resolution["workflow"])
        selected = spec.workflow
        skill = (
            skill_registry.resolve(resolution["primary_skill"])
            if resolution["primary_skill"] is not None
            else None
        )
        if skill is not None and skill.workflow != selected:
            raise ValueError("Skill workflow does not match compatibility spec")
        allowed_capabilities = (
            skill.allowed_capabilities
            if skill is not None
            else spec.allowed_capabilities
        )
        deadline_seconds = (
            skill.budgets.deadline_seconds
            if skill is not None
            else spec.budgets.deadline_seconds
        )
        max_model_calls = (
            skill.budgets.max_model_calls
            if skill is not None
            else spec.budgets.max_model_calls
        )
        max_tool_calls = (
            skill.budgets.max_tool_calls
            if skill is not None
            else spec.budgets.max_tool_calls
        )
        route_target = (
            "confirmation_required" if resolution["requires_confirmation"] else selected
        )
        emit_runtime_event(
            "route.selected",
            requested_skill=resolution["requested_skill"],
            resolved_skills=resolution["resolved_skills"],
            primary_skill=resolution["primary_skill"],
            suggested_skill=resolution["suggested_skill"],
            confidence=resolution["confidence"],
            selection_source=resolution["selection_source"],
            requires_confirmation=resolution["requires_confirmation"],
            reason_code=resolution["reason_code"],
            skill_version=(skill.version if skill is not None else None),
            selected_workflow=selected,
            agent_name=spec.name,
            model_profile=spec.model_profile,
        )
        context_package = state.get("context_package") or {}
        if context_package:
            emit_runtime_event(
                "context.used",
                package_id=context_package.get("package_id"),
                purpose=context_package.get("purpose"),
                items=[
                    {
                        "item_id": item.get("item_id"),
                        "revision_id": item.get("revision_id"),
                        "type": item.get("type"),
                        "domain": item.get("domain"),
                    }
                    for item in context_package.get("items", [])
                ],
            )
        return {
            "selected_workflow": selected,
            "route_target": route_target,
            "agent_name": spec.name,
            "model_profile": spec.model_profile,
            "prompt_bundle": spec.prompt_bundle,
            "allowed_capabilities": allowed_capabilities,
            "deadline_seconds": deadline_seconds,
            "max_model_calls": max_model_calls,
            "max_tool_calls": max_tool_calls,
        }

    def route(state: RootState) -> str:
        return state["route_target"]

    async def confirmation_required(state: RootState):
        resolution = state["skill_resolution"]
        suggested = resolution["suggested_skill"]
        labels = {"research": "深度研究", "fortune": "命理分析"}
        label = labels.get(suggested, "建议的 Skill")
        answer = f"这个请求可能更适合使用{label}。确认后我会在下一条消息中执行。"
        emit_runtime_event(
            "confirmation.required",
            suggested_skill=suggested,
            confidence=resolution["confidence"],
            reason_code=resolution["reason_code"],
        )
        emit_runtime_event(
            "answer.delta",
            text=answer,
            stage="root.confirmation",
        )
        return {"answer": answer}

    async def finalize(state: RootState, config: RunnableConfig):
        await context_from_config(config).ensure_active()
        answer = state.get("answer", "")
        if not answer:
            raise RuntimeError("workflow completed without an answer")
        completion = {
            "done": True,
            "reason": "answered",
            "workflow": state["selected_workflow"],
        }
        emit_runtime_event("workflow.completed", **completion)
        return {"completion": completion}

    graph = StateGraph(RootState)
    graph.add_node("normalize_and_route", normalize_and_route)
    graph.add_node("chat_v1", chat)
    graph.add_node("research_v1", research)
    graph.add_node("fortune_v1", fortune)
    graph.add_node("confirmation_required", confirmation_required)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "normalize_and_route")
    graph.add_conditional_edges(
        "normalize_and_route",
        route,
        {
            "chat_v1": "chat_v1",
            "research_v1": "research_v1",
            "fortune_v1": "fortune_v1",
            "confirmation_required": "confirmation_required",
        },
    )
    graph.add_edge("chat_v1", "finalize")
    graph.add_edge("research_v1", "finalize")
    graph.add_edge("fortune_v1", "finalize")
    graph.add_edge("confirmation_required", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(
        checkpointer=checkpointer,
        name="qidian_root_v1",
    )
