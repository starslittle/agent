from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from .models import (
    AgentEvent,
    AgentRunRequest,
    RunSnapshot,
    RunStatus,
    can_transition,
)


@dataclass
class Execution:
    request: AgentRunRequest
    status: RunStatus = RunStatus.QUEUED
    events: list[AgentEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=30)
    )
    error: dict | None = None

    @property
    def last_sequence(self) -> int:
        return self.events[-1].sequence if self.events else 0


class IdempotencyConflictError(RuntimeError):
    pass


class ExecutionNotFoundError(LookupError):
    pass


class ExecutionRegistry:
    """Single-replica execution registry with bounded terminal retention."""

    def __init__(self, runtime, *, service_version: str, retention_seconds: int = 1800):
        self._runtime = runtime
        self._service_version = service_version
        self._retention = timedelta(seconds=max(60, retention_seconds))
        self._executions: dict[str, Execution] = {}
        self._lock = asyncio.Lock()

    async def start(self, request: AgentRunRequest) -> Execution:
        await self._purge_expired()
        async with self._lock:
            existing = self._executions.get(request.execution_id)
            if existing is not None:
                if (
                    existing.request.idempotency_key != request.idempotency_key
                    or existing.request.run_id != request.run_id
                ):
                    raise IdempotencyConflictError(request.execution_id)
                return existing
            execution = Execution(
                request=request,
                expires_at=datetime.now(timezone.utc) + self._retention,
            )
            self._executions[request.execution_id] = execution
            execution.task = asyncio.create_task(
                self._run(execution),
                name=f"agent-run:{request.execution_id}",
            )
            return execution

    async def get(self, execution_id: str) -> Execution:
        await self._purge_expired()
        async with self._lock:
            execution = self._executions.get(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        return execution

    async def snapshot(self, execution_id: str) -> RunSnapshot:
        execution = await self.get(execution_id)
        return RunSnapshot(
            service_version=self._service_version,
            execution_id=execution.request.execution_id,
            run_id=execution.request.run_id,
            status=execution.status,
            last_sequence=execution.last_sequence,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            expires_at=execution.expires_at,
            error=execution.error,
        )

    async def cancel(self, execution_id: str) -> RunSnapshot:
        execution = await self.get(execution_id)
        if execution.status.terminal:
            return await self.snapshot(execution_id)
        was_queued = execution.status == RunStatus.QUEUED
        if execution.status != RunStatus.CANCEL_REQUESTED:
            await self._transition(execution, RunStatus.CANCEL_REQUESTED)
            await self._publish(
                execution,
                "run.cancel_requested",
                {"status": RunStatus.CANCEL_REQUESTED.value},
            )
        execution.cancel_event.set()
        if (
            not was_queued
            and execution.task is not None
            and not execution.task.done()
        ):
            execution.task.cancel()
        return await self.snapshot(execution_id)

    async def events(
        self,
        execution: Execution,
        *,
        starting_after: int = 0,
    ) -> AsyncIterator[AgentEvent]:
        cursor = max(0, starting_after)
        while True:
            async with execution.condition:
                await execution.condition.wait_for(
                    lambda: execution.last_sequence > cursor
                    or execution.status.terminal
                )
                pending = [
                    event for event in execution.events if event.sequence > cursor
                ]
                terminal = execution.status.terminal
            for event in pending:
                cursor = event.sequence
                yield event
            if terminal and cursor >= execution.last_sequence:
                return

    async def _run(self, execution: Execution) -> None:
        request = execution.request
        try:
            if execution.cancel_event.is_set() or (
                execution.status == RunStatus.CANCEL_REQUESTED
            ):
                raise asyncio.CancelledError
            await self._transition(execution, RunStatus.RUNNING)
            execution.started_at = datetime.now(timezone.utc)
            await self._publish(
                execution,
                "run.started",
                {
                    "status": RunStatus.RUNNING.value,
                    "service_version": self._service_version,
                    "agent_name": request.agent_name,
                    "model_name": getattr(self._runtime, "model_name", ""),
                },
            )
            async with asyncio.timeout(request.deadline_ms / 1000):
                async for event_type, data in self._runtime.stream(
                    request,
                    execution.cancel_event,
                ):
                    if execution.cancel_event.is_set():
                        raise asyncio.CancelledError
                    await self._publish(execution, event_type, data)
            await self._transition(execution, RunStatus.COMPLETED)
            await self._publish(
                execution,
                "run.completed",
                {"status": RunStatus.COMPLETED.value},
            )
        except TimeoutError:
            await self._transition(execution, RunStatus.TIMED_OUT)
            execution.error = {
                "code": "runtime_deadline_exceeded",
                "stage": "runtime",
                "retryable": True,
            }
            await self._publish(
                execution,
                "run.timed_out",
                {"status": RunStatus.TIMED_OUT.value, **execution.error},
            )
        except asyncio.CancelledError:
            if execution.status != RunStatus.CANCEL_REQUESTED:
                await self._transition(execution, RunStatus.CANCEL_REQUESTED)
            await self._runtime.cancel(request.execution_id)
            await self._transition(execution, RunStatus.CANCELLED)
            await self._publish(
                execution,
                "run.cancelled",
                {"status": RunStatus.CANCELLED.value},
            )
        except Exception as exc:
            await self._transition(execution, RunStatus.FAILED)
            execution.error = {
                "code": "agent_runtime_failed",
                "stage": "runtime",
                "retryable": False,
                "message": str(exc)[:1000],
            }
            await self._publish(
                execution,
                "run.failed",
                {"status": RunStatus.FAILED.value, **execution.error},
            )
        finally:
            execution.completed_at = datetime.now(timezone.utc)
            execution.expires_at = execution.completed_at + self._retention
            async with execution.condition:
                execution.condition.notify_all()

    async def _transition(
        self,
        execution: Execution,
        target: RunStatus,
    ) -> None:
        if not can_transition(execution.status, target):
            raise RuntimeError(
                f"invalid run transition {execution.status.value} -> {target.value}"
            )
        execution.status = target

    async def _publish(
        self,
        execution: Execution,
        event_type: str,
        data: dict | None = None,
    ) -> AgentEvent:
        event = AgentEvent.create(
            execution_id=execution.request.execution_id,
            run_id=execution.request.run_id,
            sequence=execution.last_sequence + 1,
            event_type=event_type,
            data=data,
        )
        async with execution.condition:
            execution.events.append(event)
            execution.condition.notify_all()
        return event

    async def _purge_expired(self) -> None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [
                execution_id
                for execution_id, execution in self._executions.items()
                if execution.status.terminal and execution.expires_at <= now
            ]
            for execution_id in expired:
                self._executions.pop(execution_id, None)
