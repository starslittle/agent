from __future__ import annotations

import asyncio
from collections import defaultdict

import pytest

from app.runtime.coordination import RuntimeSignal
from app.runtime.models import AgentRunRequest, RunStatus
from app.runtime.registry import ExecutionRegistry
from app.runtime.store import InMemoryRuntimeStore


class LocalNotifier:
    def __init__(self):
        self.queues = defaultdict(list)

    async def publish_cancel(self, execution_id):
        await self._publish(RuntimeSignal("cancel", execution_id))

    async def publish_event(self, execution_id, sequence):
        await self._publish(
            RuntimeSignal("event", execution_id, sequence=sequence)
        )

    async def _publish(self, signal):
        for queue in list(self.queues[signal.execution_id]):
            await queue.put(signal)

    async def subscribe(self, execution_id):
        queue = asyncio.Queue()
        self.queues[execution_id].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self.queues[execution_id].remove(queue)

    async def validate_ready(self):
        return {"kind": "local", "ready": True}

    async def close(self):
        return None


def _request(execution_id: str) -> AgentRunRequest:
    return AgentRunRequest(
        execution_id=execution_id,
        run_id=f"run-{execution_id}",
        request_id=f"request-{execution_id}",
        idempotency_key=f"idem-{execution_id}",
        conversation_id="conversation",
        query="wait",
    )


@pytest.mark.asyncio
async def test_notifier_accelerates_remote_cancel_but_store_is_authoritative():
    class BlockingRuntime:
        def __init__(self):
            self.entered = asyncio.Event()

        async def stream(self, request, cancel_event):
            self.entered.set()
            await asyncio.sleep(30)
            yield "answer.delta", {"text": "late"}

        async def cancel(self, execution_id):
            return None

    store = InMemoryRuntimeStore()
    notifier = LocalNotifier()
    runtime = BlockingRuntime()
    owner = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        notifier=notifier,
        owner_id="owner",
        lease_seconds=30,
        event_poll_seconds=5,
    )
    remote = ExecutionRegistry(
        runtime,
        service_version="test",
        store=store,
        notifier=notifier,
        owner_id="remote",
        lease_seconds=30,
        event_poll_seconds=5,
    )
    request = _request("exec-notified-cancel")

    await owner.start(request)
    await runtime.entered.wait()
    attached = await remote.start(request)
    await asyncio.sleep(0)
    await remote.cancel(request.execution_id)
    events = await asyncio.wait_for(
        _collect(remote, attached),
        timeout=1,
    )

    assert [event.type for event in events] == [
        "run.started",
        "run.cancel_requested",
        "run.cancelled",
    ]
    assert (await store.get_execution(request.execution_id)).status == (
        RunStatus.CANCELLED
    )


async def _collect(registry, execution):
    return [event async for event in registry.events(execution)]
