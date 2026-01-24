from __future__ import annotations

import asyncio
from typing import Any, Dict



class GraphExecutor:
    """LangGraph 执行器包装，提供 invoke/stream 兼容接口。"""

    def __init__(self, mode_hint: str | None = None, force_route: str | None = None):
        self._mode_hint = mode_hint
        self._force_route = force_route

    async def ainvoke(self, params: Dict[str, Any]):
        from graph import run_graph
        query = params.get("input") or params.get("query") or ""
        chat_history = params.get("chat_history") or []
        result = await run_graph(
            query=query,
            chat_history=chat_history,
            mode_hint=self._mode_hint,
            force_route=self._force_route,
        )
        answer = result.get("final_answer") or result.get("output", "")
        if "output" not in result:
            result = {**result, "output": answer}
        return result

    def invoke(self, params: Dict[str, Any]):
        return _run_async(self.ainvoke(params))

    async def astream(self, params: Dict[str, Any]):
        from graph import stream_graph
        query = params.get("input") or params.get("query") or ""
        chat_history = params.get("chat_history") or []
        async for chunk in stream_graph(
            query=query,
            chat_history=chat_history,
            mode_hint=self._mode_hint,
            force_route=self._force_route,
        ):
            if isinstance(chunk, dict):
                if "output" not in chunk:
                    output = chunk.get("final_answer") or chunk.get("output", "")
                    chunk = {**chunk, "output": output}
                yield chunk
            else:
                yield {"output": str(chunk)}

    def stream(self, params: Dict[str, Any]):
        return self.astream(params)


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError(
            "GraphExecutor.invoke 不可在事件循环中调用，请改用 await executor.ainvoke()"
        )
    return asyncio.run(coro)


def _resolve_force_route(agent_name: str | None, config: Dict[str, Any]) -> str | None:
    mode = str((config or {}).get("mode", "")).strip().lower()
    if mode in {"direct", "simple", "llm"}:
        return "default"
    if agent_name in {"fortune_agent", "fortune"}:
        return "fortune"
    if agent_name in {"research_agent", "research", "general_rag_agent"}:
        return "research"
    return None


def _resolve_mode_hint(agent_name: str | None) -> str | None:
    if agent_name in {"fortune_agent", "fortune"}:
        return "fortune"
    if agent_name in {"research_agent", "research", "general_rag_agent"}:
        return "research"
    return None


def create_agent_from_config(
    config: Dict[str, Any],
    streaming_override: bool | None = None,
    agent_name: str | None = None,
) -> GraphExecutor:
    _ = streaming_override
    force_route = _resolve_force_route(agent_name, config or {})
    mode_hint = _resolve_mode_hint(agent_name)
    return GraphExecutor(mode_hint=mode_hint, force_route=force_route)
