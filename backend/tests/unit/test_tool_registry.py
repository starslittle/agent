from __future__ import annotations

import asyncio

from agent.tools import registry as registry_module
from agent.tools import weather as weather_module
from agent.tools.registry import ToolDefinition, ToolRegistry, get_tool_registry


def test_registry_exposes_only_target_capabilities_and_policy_metadata():
    capabilities = {
        item["name"]: item for item in get_tool_registry().capabilities()
    }
    assert set(capabilities) == {
        "get_current_date",
        "tavily_search",
        "web_search",
        "get_weather",
        "get_lunar_chart",
        "get_ziwei_chart",
    }
    assert capabilities["get_current_date"]["effect"] == "read"
    assert capabilities["get_current_date"]["shadow_allowed"] is True
    assert all(item["idempotent"] for item in capabilities.values())
    assert all(
        item["concurrency_class"] == "thread"
        for item in capabilities.values()
    )


def test_registry_executes_date_with_hashed_audit_metadata():
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


def test_tavily_tool_uses_bounded_direct_http_request(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "协议文档",
                        "content": "版本化内部事件协议",
                        "url": "https://example.invalid/protocol",
                    }
                ]
            }

    calls = []

    def fake_post(url, *, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setattr(
        registry_module.settings if hasattr(registry_module, "settings") else
        __import__("app.core.settings", fromlist=["settings"]).settings,
        "TAVILY_API_KEY",
        "test-key",
    )
    monkeypatch.setattr("requests.post", fake_post)

    result = registry_module._tavily_search(
        "Agent Service",
        max_results=5,
    )

    assert "协议文档" in result
    assert "https://example.invalid/protocol" in result
    assert calls[0][1]["max_results"] == 5
    assert calls[0][2] == 40


def test_weather_tool_resolves_location_and_returns_current_forecast(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    calls = []

    def fake_get(url, *, params, timeout):
        calls.append((url, params, timeout))
        if "geocoding-api" in url:
            return Response(
                {
                    "results": [
                        {
                            "name": "杭州",
                            "admin1": "浙江",
                            "country": "中国",
                            "latitude": 30.27,
                            "longitude": 120.15,
                        }
                    ]
                }
            )
        return Response(
            {
                "current": {
                    "time": "2026-08-01T12:00",
                    "temperature_2m": 33.2,
                    "apparent_temperature": 38.1,
                    "relative_humidity_2m": 61,
                    "precipitation": 0.0,
                    "weather_code": 1,
                    "wind_speed_10m": 8.4,
                },
                "daily": {
                    "time": ["2026-08-01"],
                    "weather_code": [1],
                    "temperature_2m_max": [36.0],
                    "temperature_2m_min": [27.0],
                    "precipitation_probability_max": [20],
                    "sunrise": ["2026-08-01T05:17"],
                    "sunset": ["2026-08-01T18:54"],
                },
            }
        )

    monkeypatch.setattr("requests.get", fake_get)

    result = weather_module.get_weather("杭州")

    assert "杭州，浙江，中国" in result
    assert "当前温度：33.2°C" in result
    assert "今日最高/最低：36.0°C / 27.0°C" in result
    assert "Open-Meteo" in result
    assert calls[0][1]["name"] == "杭州"
    assert calls[1][1]["forecast_days"] == 1
