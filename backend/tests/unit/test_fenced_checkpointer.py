from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agent.context import RUNTIME_LEASE_KEY, RuntimeLease
from app.runtime.checkpointer import FencedAsyncCheckpointer


class FakeAsyncSaver:
    def __init__(self):
        self.serde = JsonPlusSerializer()
        self.metadata = None
        self.writes = None

    async def aput(self, config, checkpoint, metadata, new_versions):
        self.metadata = metadata
        return config

    async def aput_writes(
        self,
        config,
        writes,
        task_id,
        task_path="",
    ):
        self.writes = (writes, task_id, task_path)

    async def aget_tuple(self, config):
        return None

    async def alist(self, config, **kwargs):
        if False:
            yield None

    async def adelete_thread(self, thread_id):
        return None

    def get_next_version(self, current, channel):
        return "next"


class FakeLeaseStore:
    def __init__(self):
        self.held = []

    @asynccontextmanager
    async def hold_lease(self, lease):
        self.held.append(lease)
        yield


def make_config(
    *,
    thread_id: str = "exec-checkpoint",
    include_lease: bool = True,
):
    configurable = {
        "thread_id": thread_id,
        "checkpoint_ns": "",
    }
    if include_lease:
        configurable[RUNTIME_LEASE_KEY] = RuntimeLease(
            execution_id="exec-checkpoint",
            owner_id="worker-a",
            lease_epoch=7,
            lease_expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=30)
            ),
        )
    return {"configurable": configurable}


@pytest.mark.asyncio
async def test_checkpoint_writes_hold_lease_and_record_epoch():
    delegate = FakeAsyncSaver()
    lease_store = FakeLeaseStore()
    checkpointer = FencedAsyncCheckpointer(delegate, lease_store)
    config = make_config()

    returned = await checkpointer.aput(
        config,
        {"id": "checkpoint-1"},
        {"source": "loop"},
        {},
    )
    await checkpointer.aput_writes(
        config,
        [("channel", "value")],
        "task-1",
        "path-1",
    )

    assert returned is config
    assert len(lease_store.held) == 2
    assert delegate.metadata["runtime_lease_epoch"] == 7
    assert delegate.metadata["runtime_owner_id"] == "worker-a"
    assert delegate.writes[1:] == ("task-1", "path-1")


@pytest.mark.asyncio
async def test_checkpoint_write_fails_closed_without_matching_lease():
    checkpointer = FencedAsyncCheckpointer(
        FakeAsyncSaver(),
        FakeLeaseStore(),
    )

    with pytest.raises(RuntimeError, match="missing runtime lease"):
        await checkpointer.aput(
            make_config(include_lease=False),
            {"id": "checkpoint-1"},
            {},
            {},
        )
    with pytest.raises(RuntimeError, match="does not match"):
        await checkpointer.aput_writes(
            make_config(thread_id="different-execution"),
            [],
            "task-1",
        )
