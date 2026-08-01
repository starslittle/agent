from __future__ import annotations

import asyncio
import importlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.observability import new_span_id, payload_fingerprint


Effect = Literal["read", "write", "destructive"]
ConcurrencyClass = Literal["thread"]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: str
    effect: Effect
    idempotent: bool
    shadow_allowed: bool
    timeout_seconds: int
    max_input_bytes: int
    max_output_bytes: int
    concurrency_class: ConcurrencyClass


class ToolRegistry:
    def __init__(self, definitions: list[ToolDefinition]) -> None:
        self._definitions = {item.name: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("duplicate tool name")
        for item in definitions:
            if item.effect == "destructive" and item.shadow_allowed:
                raise ValueError(f"destructive tool {item.name} cannot allow shadow")
            if min(
                item.timeout_seconds,
                item.max_input_bytes,
                item.max_output_bytes,
            ) <= 0:
                raise ValueError(f"tool {item.name} requires finite resource limits")

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise LookupError(f"unknown tool: {name}") from exc

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in asdict(item).items()
                if key != "handler"
            }
            for item in sorted(self._definitions.values(), key=lambda item: item.name)
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        execution_id: str,
        shadow: bool = False,
        cancel_event: asyncio.Event | None = None,
        audit_events: list[dict[str, Any]] | None = None,
    ) -> str:
        definition = self.get(name)
        if shadow and not (
            definition.effect == "read" and definition.shadow_allowed
        ):
            raise PermissionError(f"tool {name} is not allowed in shadow runs")
        encoded = json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8")
        if len(encoded) > definition.max_input_bytes:
            raise ValueError(f"tool {name} input exceeds limit")

        span_id = new_span_id()
        started_at = time.perf_counter()
        audit_base = {
            "span_id": span_id,
            "span_type": "tool",
            "stage": "tool",
            "name": name,
            "effect": definition.effect,
            "idempotent": definition.idempotent,
            "concurrency_class": definition.concurrency_class,
            "content_capture_level": "hashed",
            "input": payload_fingerprint(arguments),
        }
        if audit_events is not None:
            audit_events.append({**audit_base, "status": "started"})
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(invoke_tool_sync, name, arguments),
                timeout=definition.timeout_seconds,
            )
            text = str(result)
            if len(text.encode("utf-8")) > definition.max_output_bytes:
                raise ValueError(f"tool {name} output exceeds limit")
        except asyncio.CancelledError:
            if audit_events is not None:
                audit_events.append(
                    {
                        **audit_base,
                        "status": "cancelled",
                        "duration_ms": int(
                            (time.perf_counter() - started_at) * 1000
                        ),
                    }
                )
            raise
        except Exception as exc:
            if audit_events is not None:
                audit_events.append(
                    {
                        **audit_base,
                        "status": "failed",
                        "duration_ms": int(
                            (time.perf_counter() - started_at) * 1000
                        ),
                        "error_code": type(exc).__name__[:128],
                    }
                )
            raise
        if audit_events is not None:
            audit_events.append(
                {
                    **audit_base,
                    "status": "completed",
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "output": payload_fingerprint(text),
                }
            )
        return text

    async def cancel_execution(self, execution_id: str) -> None:
        return None


def _load_handler(path: str):
    module_name, attribute = path.rsplit(":", 1)
    return getattr(importlib.import_module(module_name), attribute)


def _tavily_search(query: str, max_results: int = 5) -> str:
    import requests

    from app.core.settings import settings

    if not settings.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "max_results": max(1, min(int(max_results), 10)),
            "search_depth": "basic",
        },
        timeout=40,
    )
    response.raise_for_status()
    results = response.json()
    items = results.get("results", []) if isinstance(results, dict) else []
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title") or ""
            content = item.get("content") or item.get("snippet") or ""
            url = item.get("url") or item.get("link") or ""
            lines.append(f"- {title}: {content} ({url})")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


def invoke_tool_sync(name: str, arguments: dict[str, Any]) -> Any:
    definition = get_tool_registry().get(name)
    handler = _load_handler(definition.handler)
    if name in {"tavily_search", "web_search"}:
        return handler(**arguments)
    if hasattr(handler, "invoke"):
        return handler.invoke(arguments)
    return handler(**arguments)


_REGISTRY: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        standard_limit = 256 * 1024
        _REGISTRY = ToolRegistry(
            [
                ToolDefinition(
                    "get_current_date",
                    "返回服务端当前日期。",
                    "agent.tools.date:get_current_date",
                    "read",
                    True,
                    True,
                    15,
                    1024,
                    4096,
                    "thread",
                ),
                ToolDefinition(
                    "tavily_search",
                    "历史兼容的通用互联网搜索。",
                    "agent.tools.registry:_tavily_search",
                    "read",
                    True,
                    True,
                    45,
                    32 * 1024,
                    standard_limit,
                    "thread",
                ),
                ToolDefinition(
                    "web_search",
                    "通用互联网搜索。",
                    "agent.tools.registry:_tavily_search",
                    "read",
                    True,
                    True,
                    45,
                    32 * 1024,
                    standard_limit,
                    "thread",
                ),
                ToolDefinition(
                    "get_weather",
                    "返回指定地点的当前天气和当日预报。",
                    "agent.tools.weather:get_weather",
                    "read",
                    True,
                    True,
                    30,
                    8 * 1024,
                    32 * 1024,
                    "thread",
                ),
                ToolDefinition(
                    "get_lunar_chart",
                    "生成八字和农历排盘。",
                    "agent.tools.lunar_chart:get_lunar_chart",
                    "read",
                    True,
                    False,
                    30,
                    32 * 1024,
                    standard_limit,
                    "thread",
                ),
                ToolDefinition(
                    "get_ziwei_chart",
                    "生成紫微斗数排盘。",
                    "agent.tools.ziwei_chart:get_ziwei_chart",
                    "read",
                    True,
                    False,
                    30,
                    32 * 1024,
                    standard_limit,
                    "thread",
                ),
            ]
        )
    return _REGISTRY
