from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.observability import new_span_id
from agent.context import RunContext
from agent.tools.registry import ToolRegistry, get_tool_registry


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TavilySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    max_results: int = Field(default=5, ge=1, le=10)


class WeatherInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=2, max_length=128)


class BirthChartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_date: str = Field(
        min_length=8,
        max_length=32,
        pattern=r"^\d{4}(?:[-/年]?\d{1,2})(?:[-/月]?\d{1,2})日?$",
    )
    birth_time: str = Field(
        min_length=4,
        max_length=8,
        pattern=r"^\d{1,2}:\d{2}(?::\d{2})?$",
    )
    gender: str = Field(min_length=1, max_length=16)
    birthplace: str = Field(min_length=1, max_length=128)


class TextCapabilityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    content: str


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    snippet: str = ""


class SearchCapabilityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["search_results"] = "search_results"
    items: list[SearchResultItem]


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    output: TextCapabilityOutput | SearchCapabilityOutput
    duration_ms: int = Field(ge=0)
    idempotency_key: str


CapabilityEventSink = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    input_type: type[BaseModel]
    output_type: type[BaseModel]
    version: str
    effect: Literal["read", "write", "destructive"]
    idempotent: bool
    shadow_allowed: bool

    def input_json_schema(self) -> dict:
        return self.input_type.model_json_schema()


TARGET_CAPABILITY_SPECS: dict[str, CapabilitySpec] = {
    item.name: item
    for item in (
        CapabilitySpec(
            "get_current_date",
            EmptyInput,
            TextCapabilityOutput,
            "1",
            "read",
            True,
            True,
        ),
        CapabilitySpec(
            "tavily_search",
            TavilySearchInput,
            SearchCapabilityOutput,
            "1",
            "read",
            True,
            True,
        ),
        CapabilitySpec(
            "web_search",
            TavilySearchInput,
            SearchCapabilityOutput,
            "1",
            "read",
            True,
            True,
        ),
        CapabilitySpec(
            "get_weather",
            WeatherInput,
            TextCapabilityOutput,
            "1",
            "read",
            True,
            True,
        ),
        CapabilitySpec(
            "get_lunar_chart",
            BirthChartInput,
            TextCapabilityOutput,
            "1",
            "read",
            True,
            False,
        ),
        CapabilitySpec(
            "get_ziwei_chart",
            BirthChartInput,
            TextCapabilityOutput,
            "1",
            "read",
            True,
            False,
        ),
    )
}


def target_capability_schemas() -> list[dict]:
    return [
        {
            "name": item.name,
            "version": item.version,
            "effect": item.effect,
            "idempotent": item.idempotent,
            "shadow_allowed": item.shadow_allowed,
            "input_schema": item.input_json_schema(),
            "output_schema": item.output_type.model_json_schema(),
        }
        for item in sorted(
            TARGET_CAPABILITY_SPECS.values(),
            key=lambda value: value.name,
        )
    ]


class CapabilityExecutor(Protocol):
    async def execute(
        self,
        name: str,
        arguments: dict,
        *,
        context: RunContext,
        allowed_capabilities: list[str],
        stage: str,
        event_sink: CapabilityEventSink | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> CapabilityResult: ...


class CapabilityExecutionError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(f"capability execution failed: {code}")
        self.code = code
        self.retryable = retryable

def _emit(
    sink: CapabilityEventSink | None,
    event_type: str,
    data: dict[str, Any],
) -> None:
    if sink is not None:
        sink(event_type, data)


def _idempotency_key(
    execution_id: str,
    name: str,
    arguments: dict[str, Any],
) -> str:
    canonical = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        f"{execution_id}\n{name}\n{canonical}".encode("utf-8")
    ).hexdigest()


_SEARCH_LINE = re.compile(
    r"^-\s*(?P<title>.*?):\s*(?P<snippet>.*)\s+\((?P<url>https?://[^)]+)\)$"
)


def _normalize_output(
    spec: CapabilitySpec,
    raw_output: Any,
) -> BaseModel:
    if spec.output_type is SearchCapabilityOutput:
        items = []
        for line in str(raw_output).splitlines():
            matched = _SEARCH_LINE.match(line.strip())
            if matched:
                items.append(SearchResultItem(**matched.groupdict()))
        return SearchCapabilityOutput(items=items)
    return spec.output_type.model_validate({"content": str(raw_output)})


class RegistryCapabilityExecutor:
    """Narrow adapter around the legacy registry until CapabilitySpec lands."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self._registry = registry or get_tool_registry()

    async def execute(
        self,
        name: str,
        arguments: dict,
        *,
        context: RunContext,
        allowed_capabilities: list[str],
        stage: str,
        event_sink: CapabilityEventSink | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        await context.ensure_active()
        if name not in allowed_capabilities:
            raise PermissionError(f"capability {name} is not allowed")
        try:
            spec = TARGET_CAPABILITY_SPECS[name]
        except KeyError as exc:
            raise LookupError(f"capability has no target schema: {name}") from exc
        validated_arguments = spec.input_type.model_validate(arguments)
        normalized_arguments = validated_arguments.model_dump(exclude_none=True)
        definition = self._registry.get(name)
        if (
            definition.effect != spec.effect
            or definition.idempotent != spec.idempotent
            or definition.shadow_allowed != spec.shadow_allowed
        ):
            raise RuntimeError(f"capability policy mismatch for {name}")
        if context.shadow and not (
            spec.effect == "read" and spec.shadow_allowed
        ):
            raise PermissionError(
                f"capability {name} is not allowed in shadow runs"
            )
        timeout_seconds = min(
            float(definition.timeout_seconds),
            context.remaining_seconds,
        )
        if timeout_seconds <= 0:
            raise TimeoutError("run deadline exceeded")
        idempotency_key = _idempotency_key(
            context.execution_id,
            name,
            normalized_arguments,
        )
        span_id = new_span_id()
        event_base = {
            "span_id": span_id,
            "span_type": "tool",
            "stage": stage,
            "name": name,
            "capability_version": spec.version,
            "effect": spec.effect,
            "idempotent": spec.idempotent,
            "idempotency_key": idempotency_key,
            **(event_metadata or {}),
        }
        _emit(event_sink, "tool.started", event_base)
        started_at = time.perf_counter()
        try:
            await context.ensure_active()
            async with asyncio.timeout(timeout_seconds):
                raw_output = await self._registry.execute(
                    name,
                    normalized_arguments,
                    execution_id=context.execution_id,
                    shadow=context.shadow,
                    cancel_event=context.cancel_event,
                )
            context.raise_if_stopped()
            output = _normalize_output(spec, raw_output)
        except asyncio.CancelledError:
            _emit(
                event_sink,
                "tool.cancelled",
                {
                    **event_base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                },
            )
            raise
        except TimeoutError as exc:
            _emit(
                event_sink,
                "tool.failed",
                {
                    **event_base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "error_code": "capability_deadline_exceeded",
                    "retryable": spec.idempotent,
                },
            )
            raise CapabilityExecutionError(
                "capability_deadline_exceeded",
                retryable=spec.idempotent,
            ) from exc
        except Exception as exc:
            _emit(
                event_sink,
                "tool.failed",
                {
                    **event_base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "error_code": type(exc).__name__[:128],
                    "retryable": False,
                },
            )
            raise
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _emit(
            event_sink,
            "tool.completed",
            {**event_base, "duration_ms": duration_ms},
        )
        return CapabilityResult(
            name=name,
            output=output,
            duration_ms=duration_ms,
            idempotency_key=idempotency_key,
        )
