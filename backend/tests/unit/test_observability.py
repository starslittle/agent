from __future__ import annotations

import asyncio

from app.observability import (
    build_model_trace,
    payload_fingerprint,
    sanitize_event_data,
)
from app.observability.traces import extract_model_usage
from app.runtime.models import AgentRunRequest
from app.runtime.registry import ExecutionRegistry


def test_redaction_removes_credentials_and_bounds_content():
    clean = sanitize_event_data(
        {
            "api_key": "live-secret",
            "nested": {"Authorization": "Bearer credential"},
            "safe": "visible",
            "input_tokens": 12,
            "error": (
                "Bearer abc.def "
                "postgres://user:database-password@db/agent "
                "https://example.test/?api_key=should-hide"
            ),
            "long": "字" * 520,
        }
    )
    assert clean["api_key"] == "[redacted]"
    assert clean["nested"]["Authorization"] == "[redacted]"
    assert clean["safe"] == "visible"
    assert clean["input_tokens"] == 12
    assert "abc.def" not in clean["error"]
    assert "database-password" not in clean["error"]
    assert "should-hide" not in clean["error"]
    assert len(clean["long"]) == 501


def test_payload_fingerprint_retains_shape_not_content():
    fingerprint = payload_fingerprint(
        {"query": "a private user question", "limit": 5}
    )
    assert fingerprint["sha256"]
    assert fingerprint["bytes"] > 0
    assert fingerprint["kind"] == "dict"
    assert "private user question" not in str(fingerprint)


def test_model_usage_supports_provider_metadata_shapes():
    class Response:
        usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 4,
            "total_tokens": 14,
        }
        response_metadata = {}

    usage = extract_model_usage(Response())
    assert usage == {
        "input_tokens": 10,
        "output_tokens": 4,
        "cached_tokens": 0,
        "total_tokens": 14,
    }
    trace = build_model_trace(
        stage="generate",
        model_name="model-test",
        started_at=0,
        response=Response(),
    )
    assert trace["span_type"] == "model"
    assert trace["content_capture_level"] == "hashed"
    assert "content" not in trace


def test_registry_applies_final_redaction_to_runtime_events():
    class FakeRuntime:
        model_name = "model-test"

        async def stream(self, request, cancel_event):
            yield "tool.completed", {
                "name": "safe-tool",
                "password": "must-not-leak",
            }

        async def cancel(self, execution_id):
            return None

    async def scenario():
        registry = ExecutionRegistry(FakeRuntime(), service_version="test")
        execution = await registry.start(
            AgentRunRequest(
                execution_id="exec-observe",
                run_id="run-observe",
                request_id="req-observe",
                idempotency_key="idem-observe",
                conversation_id="conv-observe",
                query="hello",
            )
        )
        events = [event async for event in registry.events(execution)]
        tool_event = next(
            event for event in events if event.type == "tool.completed"
        )
        assert tool_event.trace_id == "exec-observe"
        assert tool_event.category == "tool"
        assert tool_event.data["password"] == "[redacted]"

    asyncio.run(scenario())
