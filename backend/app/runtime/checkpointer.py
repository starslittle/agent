from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

from agent.context import RUNTIME_LEASE_KEY, RuntimeLease

class FencedAsyncCheckpointer(BaseCheckpointSaver):
    """Serializes checkpoint writes against execution lease takeover."""

    def __init__(self, delegate, lease_store) -> None:
        super().__init__(serde=delegate.serde)
        self._delegate = delegate
        self._lease_store = lease_store

    async def aget_tuple(
        self,
        config: RunnableConfig,
    ) -> CheckpointTuple | None:
        return await self._delegate.aget_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        async for item in self._delegate.alist(
            config,
            filter=filter,
            before=before,
            limit=limit,
        ):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        lease = self._lease_from_config(config)
        fenced_metadata = {
            **metadata,
            "runtime_lease_epoch": lease.lease_epoch,
            "runtime_owner_id": lease.owner_id,
        }
        async with self._lease_store.hold_lease(lease):
            return await self._delegate.aput(
                config,
                checkpoint,
                fenced_metadata,
                new_versions,
            )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        lease = self._lease_from_config(config)
        async with self._lease_store.hold_lease(lease):
            await self._delegate.aput_writes(
                config,
                writes,
                task_id,
                task_path,
            )

    async def adelete_thread(self, thread_id: str) -> None:
        await self._delegate.adelete_thread(thread_id)

    def get_next_version(self, current, channel):
        return self._delegate.get_next_version(current, channel)

    @staticmethod
    def _lease_from_config(config: RunnableConfig) -> RuntimeLease:
        configurable = config.get("configurable") or {}
        lease = configurable.get(RUNTIME_LEASE_KEY)
        if not isinstance(lease, RuntimeLease):
            raise RuntimeError("checkpoint write is missing runtime lease")
        thread_id = configurable.get("thread_id")
        if thread_id != lease.execution_id:
            raise RuntimeError(
                "checkpoint thread_id does not match leased execution"
            )
        return lease
