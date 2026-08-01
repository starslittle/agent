from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent.capabilities import (
    CapabilityExecutionError,
    RegistryCapabilityExecutor,
    target_capability_schemas,
)
from agent.context import RunContext
from agent.models.factory import default_model_profiles
from agent.readiness import validate_target_runtime
from agent.specs import get_agent_catalog, prompt_for


def test_agent_catalog_is_the_effective_workflow_configuration():
    catalog = get_agent_catalog()

    assert catalog.names() == [
        "default_llm_agent",
        "fortune_agent",
        "research_agent",
    ]
    chat = catalog.resolve("chat_v1")
    research = catalog.resolve("general_rag_agent")
    fortune = catalog.resolve("fortune")

    assert chat.workflow == "chat_v1"
    assert chat.allowed_capabilities == [
        "get_current_date",
        "get_weather",
        "web_search",
    ]
    assert chat.budgets.max_tool_calls == 1
    assert research.workflow == "research_v1"
    assert research.allowed_capabilities == ["web_search"]
    assert research.budgets.max_tool_calls == 5
    assert fortune.workflow == "fortune_v1"
    assert "get_lunar_chart" in fortune.allowed_capabilities
    assert prompt_for("research_v1", "plan").endswith(
        "research_plan_structured.txt"
    )
    schemas = {
        item["name"]: item
        for item in target_capability_schemas()
    }
    assert (
        schemas["web_search"]["input_schema"]["additionalProperties"]
        is False
    )
    assert "birth_date" in schemas["get_lunar_chart"]["input_schema"]["required"]
    assert "items" in schemas["web_search"]["output_schema"]["properties"]
    assert "location" in schemas["get_weather"]["input_schema"]["required"]

    profiles = {item.name: item for item in default_model_profiles()}
    assert profiles["default_chat"].extra_body == {"enable_thinking": False}
    assert profiles["default_reasoning"].extra_body == {"enable_thinking": True}


def test_target_readiness_compiles_graph_and_validates_references():
    report = validate_target_runtime()

    assert report["graph"] == "qidian_root_v1"
    assert report["workflows"] == [
        "chat_v1",
        "research_v1",
        "fortune_v1",
    ]
    assert "web_search" in report["capabilities"]
    assert "get_weather" in report["capabilities"]


@pytest.mark.asyncio
async def test_capability_executor_enforces_agent_allowlist_before_registry():
    class FakeRegistry:
        def __init__(self):
            self.calls = []

        def get(self, name):
            return SimpleNamespace(
                timeout_seconds=2,
                effect="read",
                idempotent=True,
                shadow_allowed=True,
            )

        async def execute(self, name, arguments, **kwargs):
            self.calls.append((name, arguments, kwargs))
            return (
                "- 测试来源: 测试摘要 "
                "(https://example.invalid/source)"
            )

    registry = FakeRegistry()
    executor = RegistryCapabilityExecutor(registry)
    context = RunContext(
        execution_id="exec-policy",
        shadow=False,
        cancel_event=asyncio.Event(),
        deadline_at=time.monotonic() + 10,
    )

    with pytest.raises(PermissionError, match="not allowed"):
        await executor.execute(
            "get_lunar_chart",
            {},
            context=context,
            allowed_capabilities=["tavily_search"],
            stage="test",
        )
    assert registry.calls == []

    result = await executor.execute(
        "tavily_search",
        {"query": "test"},
        context=context,
        allowed_capabilities=["tavily_search"],
        stage="test",
    )
    assert result.output.items[0].title == "测试来源"
    assert result.output.items[0].url == "https://example.invalid/source"
    assert len(result.idempotency_key) == 64
    assert registry.calls[0][0] == "tavily_search"

    with pytest.raises(ValidationError):
        await executor.execute(
            "tavily_search",
            {"query": "test", "max_results": 100},
            context=context,
            allowed_capabilities=["tavily_search"],
            stage="test",
        )
    assert len(registry.calls) == 1


@pytest.mark.asyncio
async def test_capability_deadline_emits_stable_failure_and_stops_execution():
    class SlowRegistry:
        def get(self, name):
            return SimpleNamespace(
                timeout_seconds=10,
                effect="read",
                idempotent=True,
                shadow_allowed=True,
            )

        async def execute(self, name, arguments, **kwargs):
            await asyncio.sleep(10)
            return "late"

    events = []
    executor = RegistryCapabilityExecutor(SlowRegistry())
    context = RunContext(
        execution_id="exec-timeout",
        shadow=False,
        cancel_event=asyncio.Event(),
        deadline_at=time.monotonic() + 0.02,
    )

    with pytest.raises(CapabilityExecutionError) as captured:
        await executor.execute(
            "tavily_search",
            {"query": "timeout"},
            context=context,
            allowed_capabilities=["tavily_search"],
            stage="research.collect",
            event_sink=lambda event_type, data: events.append(
                (event_type, data)
            ),
        )

    assert captured.value.code == "capability_deadline_exceeded"
    assert captured.value.retryable is True
    assert [item[0] for item in events] == ["tool.started", "tool.failed"]
    assert events[0][1]["span_id"]
    assert events[0][1]["span_id"] == events[-1][1]["span_id"]
    assert events[0][1]["span_type"] == "tool"
    assert events[-1][1]["error_code"] == "capability_deadline_exceeded"


@pytest.mark.asyncio
async def test_capability_cancel_propagates_and_emits_cancelled_event():
    class CancellableRegistry:
        def get(self, name):
            return SimpleNamespace(
                timeout_seconds=10,
                effect="read",
                idempotent=True,
                shadow_allowed=True,
            )

        async def execute(self, name, arguments, *, cancel_event, **kwargs):
            await cancel_event.wait()
            raise asyncio.CancelledError

    events = []
    cancel_event = asyncio.Event()
    executor = RegistryCapabilityExecutor(CancellableRegistry())
    context = RunContext(
        execution_id="exec-cancel",
        shadow=False,
        cancel_event=cancel_event,
        deadline_at=time.monotonic() + 10,
    )
    task = asyncio.create_task(
        executor.execute(
            "tavily_search",
            {"query": "cancel"},
            context=context,
            allowed_capabilities=["tavily_search"],
            stage="research.collect",
            event_sink=lambda event_type, data: events.append(
                (event_type, data)
            ),
        )
    )
    await asyncio.sleep(0)
    cancel_event.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert [item[0] for item in events] == [
        "tool.started",
        "tool.cancelled",
    ]
    assert events[0][1]["span_id"]
    assert events[0][1]["span_id"] == events[-1][1]["span_id"]
