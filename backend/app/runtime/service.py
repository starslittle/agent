from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

from app.core.settings import settings

from .models import AgentRunRequest


class GraphAgentRuntime:
    """Protocol wrapper around the current public stream_graph behavior."""

    def __init__(self) -> None:
        self._active_tasks: dict[str, asyncio.Task] = {}
        self.model_name = settings.LLM_MODEL_NAME

    async def stream(
        self,
        request: AgentRunRequest,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, dict]]:
        from graph import stream_graph

        chat_history = [
            ("human" if item.role == "user" else "ai", item.content)
            for item in request.messages
        ]
        mode_hint = request.mode
        if mode_hint is None:
            if request.agent_name in {"research", "research_agent"}:
                mode_hint = "research"
            elif request.agent_name in {"fortune", "fortune_agent"}:
                mode_hint = "fortune"

        task = asyncio.current_task()
        if task is not None:
            self._active_tasks[request.execution_id] = task

        started = time.perf_counter()
        first_delta_at: float | None = None
        accumulated_output = ""
        last_route: str | None = None
        last_plan_current: str | None = None
        answer_deltas = 0
        try:
            async for state in stream_graph(
                query=request.query,
                chat_history=chat_history,
                mode_hint=mode_hint,
                runtime_metadata={
                    "execution_id": request.execution_id,
                    "shadow": request.shadow,
                    "cancel_event": cancel_event,
                },
            ):
                if cancel_event.is_set():
                    raise asyncio.CancelledError
                if not isinstance(state, dict):
                    continue

                route = str(state.get("route") or "default")
                if route != last_route:
                    last_route = route
                    yield "route.selected", {
                        "requested_agent": request.agent_name,
                        "actual_route": route,
                    }

                plan_current = state.get("plan_current")
                if plan_current and plan_current != last_plan_current:
                    last_plan_current = str(plan_current)
                    yield "progress", {
                        "stage": "executor",
                        "message": last_plan_current,
                    }

                tool_traces = (
                    state.get("metadata", {}).get("tool_traces", [])
                    if isinstance(state.get("metadata"), dict)
                    else []
                )
                for trace in tool_traces:
                    trace_key = f"{trace.get('iteration')}:{trace.get('name')}"
                    seen_key = f"_emitted_{trace_key}"
                    if state.get("metadata", {}).get(seen_key):
                        continue
                    state["metadata"][seen_key] = True
                    yield "tool.completed", trace

                current_output = state.get("final_answer") or state.get("output", "")
                if current_output and current_output.startswith(accumulated_output):
                    delta = current_output[len(accumulated_output) :]
                    if delta:
                        if first_delta_at is None:
                            first_delta_at = time.perf_counter()
                        answer_deltas += 1
                        accumulated_output = current_output
                        yield "answer.delta", {"text": delta}
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            first_token_ms = (
                int((first_delta_at - started) * 1000)
                if first_delta_at is not None
                else None
            )
            yield "usage", {
                "model_name": self.model_name,
                "first_token_ms": first_token_ms,
                "total_ms": elapsed_ms,
                "answer_deltas": answer_deltas,
                "output_characters": len(accumulated_output),
            }
        finally:
            self._active_tasks.pop(request.execution_id, None)

    async def cancel(self, execution_id: str) -> None:
        from agent.tools.registry import get_tool_registry

        await get_tool_registry().cancel_execution(execution_id)
        task = self._active_tasks.get(execution_id)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
