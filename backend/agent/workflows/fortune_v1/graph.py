from __future__ import annotations

from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent.artifacts import create_inline_artifact
from agent.capabilities import CapabilityExecutor
from agent.context import context_from_config
from agent.events import emit_capability_event, emit_runtime_event
from agent.models import ModelGateway, ModelMessage, ModelRequest
from agent.specs import prompt_for
from agent.state import RootState
from agent.workflows.common import (
    conversation_messages,
    prompt_metadata,
    require_model_budget,
    stream_model_answer,
)


class BirthProfile(BaseModel):
    domain: Literal["bazi", "ziwei", "general"] = "general"
    personal_analysis: bool = False
    birth_date: str | None = None
    birth_time: str | None = None
    gender: str | None = None
    birthplace: str | None = None


def _missing_fields(profile: BirthProfile) -> list[str]:
    if not profile.personal_analysis:
        return []
    values = profile.model_dump()
    return [
        name
        for name in ("birth_date", "birth_time", "gender", "birthplace")
        if not values.get(name)
    ]


def build_fortune_workflow(
    gateway: ModelGateway,
    capability_executor: CapabilityExecutor,
):
    async def extract_profile(state: RootState):
        model_calls = require_model_budget(state)
        prompt_path = prompt_for(state["prompt_bundle"], "extract")
        system_prompt, metadata = prompt_metadata(
            state,
            stage="fortune.extract_birth_profile",
            prompt_path=prompt_path,
        )
        profile = await gateway.structured(
            state["model_profile"],
            ModelRequest(
                messages=[
                    ModelMessage(
                        role="system",
                        content=system_prompt,
                    ),
                    *conversation_messages(state),
                    ModelMessage(role="user", content=state["query"]),
                ]
            ),
            BirthProfile,
            stage="fortune.extract_birth_profile",
        )
        missing = _missing_fields(profile)
        return {
            "birth_profile": profile.model_dump(),
            "missing_fields": missing,
            "model_calls": model_calls,
            "metadata": metadata,
        }

    def after_extract(state: RootState) -> str:
        if state.get("missing_fields"):
            return "clarify"
        if state.get("birth_profile", {}).get("personal_analysis"):
            return "chart"
        return "interpret"

    async def clarify(state: RootState):
        labels = {
            "birth_date": "出生日期（请注明公历或农历）",
            "birth_time": "准确出生时间（24 小时制）",
            "gender": "性别",
            "birthplace": "出生城市",
        }
        fields = [labels[item] for item in state["missing_fields"]]
        answer = "进行个人命盘分析前，还需要：" + "、".join(fields) + "。"
        emit_runtime_event("answer.delta", text=answer, stage="fortune.clarify")
        return {"answer": answer}

    async def chart(state: RootState, config: RunnableConfig):
        run_context = context_from_config(config)
        profile = state["birth_profile"]
        capability = (
            "get_ziwei_chart"
            if profile.get("domain") == "ziwei"
            else "get_lunar_chart"
        )
        arguments = {
            key: profile.get(key)
            for key in ("birth_date", "birth_time", "gender", "birthplace")
        }
        result = await capability_executor.execute(
            capability,
            arguments,
            context=run_context,
            allowed_capabilities=state["allowed_capabilities"],
            stage="fortune.chart",
            event_sink=emit_capability_event,
        )
        content = result.output.content
        artifact = create_inline_artifact(
            artifact_type="fortune_chart",
            content=content,
            metadata={
                "domain": profile.get("domain"),
                "capability": capability,
                "capability_idempotency_key": result.idempotency_key,
            },
        )
        await run_context.stage_artifact(artifact)
        emit_runtime_event(
            "artifact.created",
            **artifact.ref.model_dump(mode="json"),
        )
        return {
            "tool_results": {capability: content},
            "artifacts": [
                *state.get("artifacts", []),
                artifact.model_dump(mode="json"),
            ],
            "tool_calls": 1,
        }

    async def interpret(state: RootState):
        context = "\n\n".join(
            f"{name}:\n{value}"
            for name, value in state.get("tool_results", {}).items()
        )
        if not context:
            context = (
                "这是概念或方法问题，没有个人排盘结果。"
                "不得虚构用户命盘，也不得给出确定性人生预测。"
            )
        return await stream_model_answer(
            gateway=gateway,
            state=state,
            profile_name=state["model_profile"],
            stage="fortune.interpret",
            prompt_path=prompt_for(state["prompt_bundle"], "generate"),
            context=context,
        )

    graph = StateGraph(RootState)
    graph.add_node("extract_birth_profile", extract_profile)
    graph.add_node("clarify", clarify)
    graph.add_node("deterministic_chart", chart)
    graph.add_node("interpret", interpret)
    graph.add_edge(START, "extract_birth_profile")
    graph.add_conditional_edges(
        "extract_birth_profile",
        after_extract,
        {
            "clarify": "clarify",
            "chart": "deterministic_chart",
            "interpret": "interpret",
        },
    )
    graph.add_edge("clarify", END)
    graph.add_edge("deterministic_chart", "interpret")
    graph.add_edge("interpret", END)
    return graph.compile(name="fortune_v1")
