from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.runtime.models import (
    AgentEvent,
    AgentRunRequest,
    RunStatus,
    can_transition,
)
from app.runtime.registry import ExecutionRegistry


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_protocol_v1_events.json"
)


def test_event_fixture_has_monotonic_sequences_and_stable_sse_ids():
    events = [
        AgentEvent.model_validate(item)
        for item in json.loads(FIXTURE.read_text(encoding="utf-8"))
    ]
    assert [event.sequence for event in events] == [1, 2, 3]
    assert events[1].sse_id == "exec_fixture_001:2"
    assert len({(event.execution_id, event.sequence) for event in events}) == 3


def test_run_state_machine_rejects_terminal_regression():
    assert can_transition(RunStatus.QUEUED, RunStatus.CANCEL_REQUESTED)
    assert can_transition(RunStatus.RUNNING, RunStatus.COMPLETED)
    assert can_transition(RunStatus.CANCEL_REQUESTED, RunStatus.CANCELLED)
    assert not can_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    assert not can_transition(RunStatus.CANCELLED, RunStatus.COMPLETED)


def test_registry_streams_terminal_run_and_reuses_idempotent_execution():
    class FakeRuntime:
        async def stream(self, request, cancel_event):
            yield "answer.delta", {"text": "ok"}

        async def cancel(self, execution_id):
            return None

    async def scenario():
        registry = ExecutionRegistry(FakeRuntime(), service_version="test")
        request = AgentRunRequest(
            execution_id="exec_1",
            run_id="run_1",
            request_id="req_1",
            idempotency_key="idem_1",
            conversation_id="conv_1",
            query="hello",
        )
        execution = await registry.start(request)
        duplicate = await registry.start(request)
        assert duplicate is execution
        events = [event async for event in registry.events(execution)]
        assert [event.type for event in events] == [
            "run.started",
            "answer.delta",
            "run.completed",
        ]
        snapshot = await registry.snapshot(request.execution_id)
        assert snapshot.status == RunStatus.COMPLETED
        assert snapshot.last_sequence == 3

    asyncio.run(scenario())


def test_registry_can_cancel_before_runtime_starts():
    class SlowRuntime:
        async def stream(self, request, cancel_event):
            await asyncio.sleep(10)
            yield "answer.delta", {"text": "late"}

        async def cancel(self, execution_id):
            return None

    async def scenario():
        registry = ExecutionRegistry(SlowRuntime(), service_version="test")
        request = AgentRunRequest(
            execution_id="exec_cancel",
            run_id="run_cancel",
            request_id="req_cancel",
            idempotency_key="idem_cancel",
            conversation_id="conv_cancel",
            query="cancel",
        )
        execution = await registry.start(request)
        await registry.cancel(request.execution_id)
        events = [event async for event in registry.events(execution)]
        assert events[-1].type == "run.cancelled"
        assert (await registry.snapshot(request.execution_id)).status == RunStatus.CANCELLED

    asyncio.run(scenario())
