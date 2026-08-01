from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from agent.artifacts import create_citation, create_json_artifact
from agent.capabilities import (
    CapabilityExecutor,
    SearchCapabilityOutput,
    TextCapabilityOutput,
)
from agent.context import context_from_config
from agent.events import emit_capability_event, emit_runtime_event
from agent.models import ModelGateway
from agent.specs import prompt_for
from agent.state import RootState
from agent.workflows.common import stream_model_answer


def _direct_context(state: RootState) -> str:
    tool_results = state.get("tool_results", {})
    if not tool_results:
        return ""
    lines = ["【本轮受控工具结果】"]
    for name, content in tool_results.items():
        lines.append(f"{name}:\n{content}")
    citations = list(
        {
            item["citation_id"]: item
            for item in state.get("citations", [])
        }.values()
    )
    if citations:
        lines.extend(
            [
                "【引用编号】",
                *[
                    f"[{item['citation_id']}] {item['title']} {item['url']}"
                    for item in citations
                ],
            ]
        )
    return "\n\n".join(lines)


def build_chat_workflow(
    gateway: ModelGateway,
    capability_executor: CapabilityExecutor,
):
    async def execute_direct_capability(
        state: RootState,
        config: RunnableConfig,
    ):
        resolution = state.get("skill_resolution", {})
        name = resolution.get("direct_capability")
        if not name:
            return {}
        if state.get("tool_calls", 0) >= state["max_tool_calls"]:
            raise RuntimeError("tool call budget exhausted")

        run_context = context_from_config(config)
        try:
            result = await capability_executor.execute(
                name,
                dict(resolution.get("direct_capability_arguments") or {}),
                context=run_context,
                allowed_capabilities=state["allowed_capabilities"],
                stage="chat.current_info",
                event_sink=emit_capability_event,
            )
        except Exception as exc:
            emit_runtime_event(
                "progress",
                stage="chat.current_info",
                capability=name,
                degraded=True,
                error_code=type(exc).__name__,
            )
            return {
                "tool_results": {
                    name: "工具调用失败；无法核实本次实时信息，请明确说明这一限制。"
                },
                "tool_calls": 1,
            }

        citations: list[dict] = []
        artifacts = list(state.get("artifacts", []))
        if isinstance(result.output, SearchCapabilityOutput):
            items = result.output.items
            citations = [
                create_citation(
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                ).model_dump(mode="json")
                for item in items
            ]
            content = "\n".join(
                f"- [{citation['citation_id']}] {item.title}: "
                f"{item.snippet} ({item.url})"
                for item, citation in zip(items, citations, strict=True)
            )
            if not content:
                content = "联网搜索没有返回可验证结果。"
            artifact = create_json_artifact(
                artifact_type="web_search_evidence",
                value={
                    "capability": name,
                    "items": result.output.model_dump(mode="json")["items"],
                    "citations": citations,
                },
                metadata={"source_count": len(citations)},
            )
            await run_context.stage_artifact(artifact)
            artifacts.append(artifact.model_dump(mode="json"))
            emit_runtime_event(
                "artifact.created",
                **artifact.ref.model_dump(mode="json"),
                citation_count=len(citations),
            )
            for sequence, citation in enumerate(citations, start=1):
                emit_runtime_event(
                    "citation.created",
                    **citation,
                    artifact_id=artifact.ref.artifact_id,
                    sequence=sequence,
                )
        elif isinstance(result.output, TextCapabilityOutput):
            content = result.output.content
        else:
            content = str(result.output)

        emit_runtime_event(
            "progress",
            stage="chat.current_info",
            capability=name,
            degraded=False,
            sources=len(citations),
        )
        return {
            "tool_results": {name: content},
            "tool_calls": 1,
            "citations": citations,
            "artifacts": artifacts,
        }

    async def model_stream(state: RootState):
        return await stream_model_answer(
            gateway=gateway,
            state=state,
            profile_name=state["model_profile"],
            stage="chat.generate",
            prompt_path=prompt_for(state["prompt_bundle"], "generate"),
            context=_direct_context(state),
        )

    graph = StateGraph(RootState)
    graph.add_node("execute_direct_capability", execute_direct_capability)
    graph.add_node("model_stream", model_stream)
    graph.add_edge(START, "execute_direct_capability")
    graph.add_edge("execute_direct_capability", "model_stream")
    graph.add_edge("model_stream", END)
    return graph.compile(name="chat_v1")
