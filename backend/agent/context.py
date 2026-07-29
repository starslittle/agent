from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


RUN_CONTEXT_KEY = "qidian_run_context"
RUNTIME_LEASE_KEY = "qidian_runtime_lease"


@dataclass(frozen=True)
class RuntimeLease:
    execution_id: str
    owner_id: str
    lease_epoch: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class RunContext:
    execution_id: str
    shadow: bool
    cancel_event: asyncio.Event
    deadline_at: float
    lease: RuntimeLease | None = None
    lease_validator: (
        Callable[[RuntimeLease], Awaitable[None]] | None
    ) = None
    artifact_stager: (
        Callable[[RuntimeLease, Any], Awaitable[None]] | None
    ) = None

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - time.monotonic())

    def raise_if_stopped(self) -> None:
        if self.cancel_event.is_set():
            raise asyncio.CancelledError
        if self.remaining_seconds <= 0:
            raise TimeoutError("run deadline exceeded")

    async def ensure_active(self) -> None:
        self.raise_if_stopped()
        if self.lease is not None and self.lease_validator is not None:
            await self.lease_validator(self.lease)
        self.raise_if_stopped()

    async def stage_artifact(self, artifact: Any) -> None:
        await self.ensure_active()
        if self.lease is not None and self.artifact_stager is not None:
            await self.artifact_stager(self.lease, artifact)
        await self.ensure_active()


def context_from_config(config: dict[str, Any]) -> RunContext:
    configurable = config.get("configurable") or {}
    context = configurable.get(RUN_CONTEXT_KEY)
    if not isinstance(context, RunContext):
        raise RuntimeError("LangGraph run context is missing")
    return context
