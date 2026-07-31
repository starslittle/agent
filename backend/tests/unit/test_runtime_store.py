from __future__ import annotations

import asyncio

import pytest

from agent.artifacts import create_inline_artifact
from app.runtime.models import AgentRunRequest, RunStatus
from app.runtime.registry import ExecutionRegistry
from app.runtime.store import (
    IdempotencyConflictError,
    InMemoryRuntimeStore,
    LeaseLostError,
    StartDisposition,
    request_fingerprint,
)


def make_request(
    *,
    execution_id: str = "exec-store",
    query: str = "测试持久运行",
    metadata: dict | None = None,
) -> AgentRunRequest:
    return AgentRunRequest(
        execution_id=execution_id,
        run_id=f"run-{execution_id}",
        request_id=f"request-{execution_id}",
        idempotency_key=f"idem-{execution_id}",
        conversation_id=f"conversation-{execution_id}",
        query=query,
        metadata=metadata or {},
    )


def test_request_fingerprint_is_canonical_and_semantic():
    first = make_request(metadata={"b": 2, "a": 1})
    second = make_request(metadata={"a": 1, "b": 2})
    changed = make_request(query="不同问题", metadata={"a": 1, "b": 2})

    assert request_fingerprint(first) == request_fingerprint(second)
    assert request_fingerprint(first) != request_fingerprint(changed)


@pytest.mark.asyncio
async def test_runtime_store_reuses_request_and_rejects_conflict():
    store = InMemoryRuntimeStore()
    request = make_request()
    created = await store.start_execution(
        request,
        owner_id="worker-a",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=60,
        retention_seconds=300,
    )
    attached = await store.start_execution(
        request,
        owner_id="worker-b",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=60,
        retention_seconds=300,
    )

    assert created.disposition == StartDisposition.CREATED
    assert created.lease is not None
    assert attached.disposition == StartDisposition.ATTACHED
    assert attached.lease is None

    with pytest.raises(IdempotencyConflictError):
        await store.start_execution(
            make_request(query="同 execution_id 的另一请求"),
            owner_id="worker-b",
            service_version="test",
            graph_version="graph-v1",
            lease_seconds=60,
            retention_seconds=300,
        )


@pytest.mark.asyncio
async def test_run_provenance_is_sealed_when_execution_is_created():
    store = InMemoryRuntimeStore()
    request = make_request(execution_id="exec-provenance")
    provenance = {
        "workflow_name": "chat_v1",
        "agent_spec_hash": "a" * 64,
        "prompt_bundle_hash": "b" * 64,
        "model_name": "configured-model",
        "capabilities": [],
    }
    created = await store.start_execution(
        request,
        owner_id="worker-a",
        service_version="test",
        graph_version="qidian-root-v1",
        lease_seconds=60,
        retention_seconds=300,
        provenance=provenance,
    )
    await store.start_execution(
        request,
        owner_id="worker-b",
        service_version="changed",
        graph_version="changed",
        lease_seconds=60,
        retention_seconds=300,
        provenance={"workflow_name": "fortune_v1"},
    )
    record = await store.get_execution(request.execution_id)

    assert created.execution.workflow_name == "chat_v1"
    assert record.provenance == provenance
    assert record.graph_version == "qidian-root-v1"


@pytest.mark.asyncio
async def test_run_started_projects_sealed_provenance():
    class ProvenanceRuntime:
        graph_version = "qidian-root-v1"

        async def describe_provenance(self, request):
            return {
                "workflow_name": "chat_v1",
                "agent_spec_hash": "a" * 64,
                "prompt_bundle_hash": "b" * 64,
                "model_profile": "default_chat",
                "model_provider": "dashscope_openai",
                "model_name": "configured-model",
            }

        async def stream(self, request, cancel_event):
            yield "answer.delta", {"text": "ok"}

        async def cancel(self, execution_id):
            return None

    store = InMemoryRuntimeStore()
    registry = ExecutionRegistry(
        ProvenanceRuntime(),
        service_version="test-service",
        store=store,
    )
    execution = await registry.start(
        make_request(execution_id="exec-provenance-event")
    )
    events = [event async for event in registry.events(execution)]
    started = next(event for event in events if event.type == "run.started")

    assert started.data["graph_version"] == "qidian-root-v1"
    assert started.data["workflow_name"] == "chat_v1"
    assert started.data["agent_version"] == "a" * 64
    assert started.data["prompt_bundle_hash"] == "b" * 64
    assert started.data["model_name"] == "configured-model"


@pytest.mark.asyncio
async def test_lease_epoch_fences_old_owner_after_takeover():
    store = InMemoryRuntimeStore()
    request = make_request(execution_id="exec-fencing")
    original = await store.start_execution(
        request,
        owner_id="worker-a",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=0,
        retention_seconds=300,
    )
    takeover = await store.start_execution(
        request,
        owner_id="worker-b",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=60,
        retention_seconds=300,
    )

    assert original.lease is not None
    assert takeover.lease is not None
    assert takeover.disposition == StartDisposition.TAKEOVER
    assert takeover.lease.lease_epoch == original.lease.lease_epoch + 1

    with pytest.raises(LeaseLostError):
        await store.append_event(
            original.lease,
            "answer.delta",
            {"text": "旧副本不得写入"},
        )

    event = await store.append_event(
        takeover.lease,
        "answer.delta",
        {"text": "新副本可以写入"},
    )
    assert event.sequence == 1


@pytest.mark.asyncio
async def test_runtime_event_outbox_replays_monotonic_sequences():
    store = InMemoryRuntimeStore()
    started = await store.start_execution(
        make_request(execution_id="exec-replay"),
        owner_id="worker-a",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=60,
        retention_seconds=300,
    )
    assert started.lease is not None
    lease = started.lease

    await store.transition(
        lease,
        RunStatus.RUNNING,
        retention_seconds=300,
    )
    await store.append_event(lease, "run.started", {"status": "running"})
    await store.append_event(lease, "answer.delta", {"text": "第一段"})
    await store.append_event(lease, "answer.delta", {"text": "第二段"})

    replayed = await store.events_after("exec-replay", 1)
    assert [event.sequence for event in replayed] == [2, 3]
    assert [event.type for event in replayed] == [
        "answer.delta",
        "answer.delta",
    ]
    assert (await store.get_execution("exec-replay")).last_sequence == 3


@pytest.mark.asyncio
async def test_runtime_artifact_staging_is_fenced_and_content_addressed():
    store = InMemoryRuntimeStore()
    started = await store.start_execution(
        make_request(execution_id="exec-artifact"),
        owner_id="worker-a",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=60,
        retention_seconds=300,
    )
    assert started.lease is not None
    artifact = create_inline_artifact(
        artifact_type="research_evidence",
        content='{"source":"verified"}',
    )

    await store.stage_artifact(started.lease, artifact)
    restored = await store.get_artifact(
        "exec-artifact",
        artifact.ref.artifact_id,
    )

    assert restored == artifact


@pytest.mark.asyncio
async def test_two_registries_share_outbox_without_duplicate_execution():
    class CoordinatedRuntime:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def stream(self, request, cancel_event):
            self.calls += 1
            self.entered.set()
            await self.release.wait()
            yield "answer.delta", {"text": "only once"}

        async def cancel(self, execution_id):
            return None

    store = InMemoryRuntimeStore()
    runtime = CoordinatedRuntime()
    first_registry = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        owner_id="worker-a",
    )
    second_registry = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        owner_id="worker-b",
        event_poll_seconds=0.01,
    )
    request = make_request(execution_id="exec-shared")

    await first_registry.start(request)
    await runtime.entered.wait()
    attached = await second_registry.start(request)
    runtime.release.set()
    events = [
        event async for event in second_registry.events(attached)
    ]

    assert runtime.calls == 1
    assert attached.disposition == StartDisposition.ATTACHED
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert events[-1].type == "run.completed"


@pytest.mark.asyncio
async def test_remote_registry_cancel_reaches_current_lease_owner():
    class BlockingRuntime:
        def __init__(self):
            self.entered = asyncio.Event()
            self.cancel_calls = 0

        async def stream(self, request, cancel_event):
            self.entered.set()
            await asyncio.sleep(10)
            yield "answer.delta", {"text": "late"}

        async def cancel(self, execution_id):
            self.cancel_calls += 1

    store = InMemoryRuntimeStore()
    runtime = BlockingRuntime()
    owner = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        owner_id="worker-a",
        lease_seconds=3,
        event_poll_seconds=0.01,
    )
    remote = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        owner_id="worker-b",
        lease_seconds=3,
        event_poll_seconds=0.01,
    )
    request = make_request(execution_id="exec-remote-cancel")

    await owner.start(request)
    await runtime.entered.wait()
    attached = await remote.start(request)
    await remote.cancel(request.execution_id)
    events = [event async for event in remote.events(attached)]

    assert [event.type for event in events] == [
        "run.resolved",
        "run.started",
        "run.cancel_requested",
        "run.cancelled",
    ]
    assert runtime.cancel_calls == 1


@pytest.mark.asyncio
async def test_takeover_fails_closed_until_checkpointer_is_available():
    class RuntimeMustNotRun:
        async def stream(self, request, cancel_event):
            raise AssertionError("takeover must not restart graph from scratch")
            yield

        async def cancel(self, execution_id):
            return None

    store = InMemoryRuntimeStore()
    request = make_request(execution_id="exec-unsafe-recovery")
    await store.start_execution(
        request,
        owner_id="expired-worker",
        service_version="test",
        graph_version="graph-v1",
        lease_seconds=0,
        retention_seconds=300,
    )
    registry = ExecutionRegistry(
        RuntimeMustNotRun(),
        service_version="test",
        store=store,
        owner_id="replacement-worker",
        event_poll_seconds=0.01,
    )

    execution = await registry.start(request)
    events = [event async for event in registry.events(execution)]

    assert execution.disposition == StartDisposition.TAKEOVER
    assert [event.type for event in events] == [
        "runtime.recovery_failed",
        "run.failed",
    ]
    assert (await registry.snapshot(request.execution_id)).status == RunStatus.FAILED


@pytest.mark.asyncio
async def test_takeover_resumes_only_when_runtime_confirms_checkpoint():
    class ResumableRuntime:
        supports_lease_context = True
        supports_checkpoint_recovery = True

        def __init__(self):
            self.resume_values = []

        async def can_resume(self, execution_id):
            return True

        async def stream(
            self,
            request,
            cancel_event,
            *,
            lease,
            resume,
        ):
            self.resume_values.append(resume)
            yield "answer.delta", {"text": "从 checkpoint 继续"}

        async def cancel(self, execution_id):
            return None

    store = InMemoryRuntimeStore()
    request = make_request(execution_id="exec-safe-recovery")
    await store.start_execution(
        request,
        owner_id="expired-worker",
        service_version="test",
        graph_version="qidian-root-v1",
        lease_seconds=0,
        retention_seconds=300,
    )
    runtime = ResumableRuntime()
    registry = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        owner_id="replacement-worker",
        event_poll_seconds=0.01,
    )

    execution = await registry.start(request)
    events = [event async for event in registry.events(execution)]

    assert runtime.resume_values == [True]
    assert [event.type for event in events] == [
        "run.resolved",
        "run.resumed",
        "answer.delta",
        "run.completed",
    ]
    assert events[1].data["lease_epoch"] == 2
    assert (await registry.snapshot(request.execution_id)).status == (
        RunStatus.COMPLETED
    )
