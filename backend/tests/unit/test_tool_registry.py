from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from agent.tools import registry as registry_module
from agent.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    get_tool_registry,
)
from agent.worker import heavy_worker_manager


def test_registry_exposes_resource_and_side_effect_metadata():
    capabilities = {
        item["name"]: item for item in get_tool_registry().capabilities()
    }
    assert capabilities["get_current_date"]["effect"] == "read"
    assert capabilities["get_current_date"]["shadow_allowed"] is True
    assert capabilities["init_local_rag"]["effect"] == "destructive"
    assert capabilities["init_local_rag"]["shadow_allowed"] is False
    assert capabilities["query_pandas_data"]["concurrency_class"] == "process"


def test_registry_executes_date_without_loading_heavy_rag_modules():
    async def scenario():
        audit_events = []
        result = await get_tool_registry().execute(
            "get_current_date",
            {},
            execution_id="exec-test",
            shadow=True,
            audit_events=audit_events,
        )
        assert "年" in result and "月" in result and "日" in result
        assert [event["status"] for event in audit_events] == [
            "started",
            "completed",
        ]
        assert audit_events[0]["span_id"] == audit_events[1]["span_id"]
        assert audit_events[0]["input"]["sha256"]
        assert "result" not in audit_events[1]
        assert audit_events[1]["output"]["sha256"]

    asyncio.run(scenario())


def test_registry_rejects_shadow_side_effect_before_invocation():
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="blocked",
                description="blocked",
                handler="agent.tools.date:get_current_date",
                effect="write",
                idempotent=True,
                shadow_allowed=False,
                timeout_seconds=1,
                max_input_bytes=10,
                max_output_bytes=100,
                concurrency_class="thread",
            )
        ]
    )

    async def scenario():
        try:
            await registry.execute(
                "blocked",
                {},
                execution_id="exec-test",
                shadow=True,
            )
        except PermissionError:
            return
        raise AssertionError("shadow write tool was not rejected")

    asyncio.run(scenario())


def test_heavy_worker_process_has_a_real_result_lifecycle():
    async def scenario():
        result = await heavy_worker_manager.run(
            execution_id="exec-worker-test",
            tool_name="get_current_date",
            arguments={},
            timeout_seconds=10,
        )
        assert "年" in result

    asyncio.run(scenario())


def test_heavy_worker_can_be_cancelled_by_execution():
    async def scenario():
        cancel_event = asyncio.Event()
        task = asyncio.create_task(
            heavy_worker_manager.run(
                execution_id="exec-worker-cancel",
                tool_name="get_current_date",
                arguments={},
                timeout_seconds=10,
                cancel_event=cancel_event,
            )
        )
        await asyncio.sleep(0.01)
        cancel_event.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_weather_tool_uses_bounded_now_and_daily_requests(monkeypatch):
    from agent.tools import weather

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        if url.endswith("/now.json"):
            return Response(
                {
                    "results": [
                        {
                            "location": {"name": "杭州"},
                            "now": {"text": "晴", "temperature": "31"},
                        }
                    ]
                }
            )
        return Response(
            {"results": [{"daily": [{"high": "34", "low": "26"}]}]}
        )

    monkeypatch.setattr(weather.settings, "SENIVERSE_API_KEY", "test-key")
    monkeypatch.setattr(weather.requests, "get", fake_get)

    result = weather.get_seniverse_weather.invoke({"location": "杭州"})

    assert result == "杭州当前天气：晴，当前温度：31°C。 最高34°C，最低26°C。"
    assert len(calls) == 2
    assert all(call[2] == 15 for call in calls)


def test_tavily_tool_normalizes_results_without_network(monkeypatch):
    class FakeTavilySearch:
        def __init__(self, *, max_results):
            assert max_results == 5

        def invoke(self, payload):
            assert payload == {"query": "Agent Service"}
            return {
                "results": [
                    {
                        "title": "协议文档",
                        "content": "版本化内部事件协议",
                        "url": "https://example.invalid/protocol",
                    }
                ]
            }

    monkeypatch.setitem(
        sys.modules,
        "langchain_tavily",
        SimpleNamespace(TavilySearch=FakeTavilySearch),
    )

    result = registry_module._tavily_search("Agent Service", max_results=5)

    assert "协议文档" in result
    assert "https://example.invalid/protocol" in result
