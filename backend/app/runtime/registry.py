from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

from .coordination import RuntimeNotifier
from .models import AgentEvent, AgentRunRequest, RunSnapshot, RunStatus
from .store import (
    ExecutionNotFoundError,
    IdempotencyConflictError,
    InMemoryRuntimeStore,
    LeaseLostError,
    LeaseToken,
    RuntimeStore,
    StartDisposition,
)


@dataclass
class Execution:
    request: AgentRunRequest
    status: RunStatus
    expires_at: datetime
    deadline_at: datetime
    provenance: dict = field(default_factory=dict)
    lease: LeaseToken | None = None
    disposition: StartDisposition = StartDisposition.ATTACHED
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    renew_task: asyncio.Task[None] | None = None
    signal_task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    lease_lost: bool = False
    abandoning: bool = False


class ExecutionRegistry:
    """Coordinates local tasks while RuntimeStore owns durable run truth."""

    def __init__(
        self,
        runtime,
        *,
        service_version: str,
        retention_seconds: int = 1800,
        store: RuntimeStore | None = None,
        owner_id: str | None = None,
        lease_seconds: int = 30,
        event_poll_seconds: float = 0.25,
        graph_version: str | None = None,
        notifier: RuntimeNotifier | None = None,
    ):
        self._runtime = runtime
        self._service_version = service_version
        self._retention_seconds = max(60, retention_seconds)
        self._store = store or InMemoryRuntimeStore()
        self._owner_id = owner_id or (
            f"{os.getenv('HOSTNAME', 'agent')}:{uuid.uuid4().hex}"
        )
        self._lease_seconds = max(3, lease_seconds)
        self._event_poll_seconds = max(0.05, event_poll_seconds)
        self._graph_version = graph_version or getattr(
            runtime,
            "graph_version",
            "qidian-root-v1",
        )
        self._notifier = notifier
        self._executions: dict[str, Execution] = {}
        self._lock = asyncio.Lock()

    @property
    def store_kind(self) -> str:
        return type(self._store).__name__

    async def validate_store(self) -> dict:
        report = await self._store.validate_ready()
        report["coordination"] = (
            await self._notifier.validate_ready()
            if self._notifier is not None
            else {"kind": "postgres_polling", "ready": True}
        )
        return report

    async def resolve_route(self, request):
        if not hasattr(self._runtime, "resolve_route"):
            raise RuntimeError("runtime route resolver unavailable")
        return await self._runtime.resolve_route(request)

    async def purge_expired(self) -> int:
        return await self._store.purge_expired()

    async def start(self, request: AgentRunRequest) -> Execution:
        await self._purge_expired()
        async with self._lock:
            provenance = {
                "service_version": self._service_version,
                "graph_version": self._graph_version,
                "protocol_version": request.protocol_version,
                **(
                    await self._runtime.describe_provenance(request)
                    if hasattr(self._runtime, "describe_provenance")
                    else {}
                ),
            }
            result = await self._store.start_execution(
                request,
                owner_id=self._owner_id,
                service_version=self._service_version,
                graph_version=self._graph_version,
                lease_seconds=self._lease_seconds,
                retention_seconds=self._retention_seconds,
                provenance=provenance,
            )
            existing = self._executions.get(request.execution_id)
            if existing is not None:
                if result.lease is not None:
                    existing.lease = result.lease
                existing.status = result.execution.status
                existing.expires_at = result.execution.expires_at
                existing.deadline_at = result.execution.deadline_at
                return existing

            execution = Execution(
                request=self._request_with_provenance(
                    request,
                    result.execution.provenance,
                ),
                status=result.execution.status,
                expires_at=result.execution.expires_at,
                deadline_at=result.execution.deadline_at,
                provenance=dict(result.execution.provenance),
                lease=result.lease,
                disposition=result.disposition,
            )
            self._executions[request.execution_id] = execution
            self._start_signal_listener(execution)
            if result.disposition == StartDisposition.CREATED:
                execution.task = asyncio.create_task(
                    self._run(execution),
                    name=f"agent-run:{request.execution_id}",
                )
            elif result.disposition in {
                StartDisposition.TAKEOVER,
                StartDisposition.OWNED,
            }:
                execution.task = asyncio.create_task(
                    self._recover_or_fail_closed(execution),
                    name=f"agent-recovery:{request.execution_id}",
                )
            return execution

    async def get(self, execution_id: str) -> Execution:
        await self._purge_expired()
        async with self._lock:
            execution = self._executions.get(execution_id)
        if execution is not None:
            return execution
        record = await self._store.get_execution(execution_id)
        execution = Execution(
            request=self._placeholder_request(record),
            status=record.status,
            expires_at=record.expires_at,
            deadline_at=record.deadline_at,
            provenance=dict(record.provenance),
            lease=None,
            disposition=(
                StartDisposition.TERMINAL_REPLAY
                if record.status.terminal
                else StartDisposition.ATTACHED
            ),
        )
        async with self._lock:
            result = self._executions.setdefault(execution_id, execution)
        self._start_signal_listener(result)
        return result

    async def snapshot(self, execution_id: str) -> RunSnapshot:
        record = await self._store.get_execution(execution_id)
        async with self._lock:
            local = self._executions.get(execution_id)
            if local is not None:
                local.status = record.status
                local.expires_at = record.expires_at
        return record.snapshot()

    async def cancel(self, execution_id: str) -> RunSnapshot:
        before = await self._store.get_execution(execution_id)
        if before.status.terminal:
            return before.snapshot()
        execution = await self.get(execution_id)
        was_queued = before.status == RunStatus.QUEUED
        record = await self._store.request_cancel(execution_id)
        if self._notifier is not None:
            await self._notifier.publish_cancel(execution_id)
        execution.status = record.status
        if execution.lease is not None:
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
        return (await self._store.get_execution(execution_id)).snapshot()

    async def events(
        self,
        execution: Execution,
        *,
        starting_after: int = 0,
    ) -> AsyncIterator[AgentEvent]:
        cursor = max(0, starting_after)
        while True:
            pending = await self._store.events_after(
                execution.request.execution_id,
                cursor,
            )
            for event in pending:
                cursor = event.sequence
                yield event
            record = await self._store.get_execution(
                execution.request.execution_id
            )
            execution.status = record.status
            execution.expires_at = record.expires_at
            if record.status.terminal and cursor >= record.last_sequence:
                return
            async with execution.condition:
                try:
                    await asyncio.wait_for(
                        execution.condition.wait(),
                        timeout=self._event_poll_seconds,
                    )
                except TimeoutError:
                    pass

    async def _run(
        self,
        execution: Execution,
        *,
        resume: bool = False,
    ) -> None:
        request = execution.request
        if execution.lease is None:
            raise RuntimeError("new execution is missing its lease")
        execution.renew_task = asyncio.create_task(
            self._renew_lease(execution),
            name=f"agent-lease:{request.execution_id}",
        )
        try:
            if execution.cancel_event.is_set() or (
                execution.status == RunStatus.CANCEL_REQUESTED
            ):
                raise asyncio.CancelledError
            await self._transition(execution, RunStatus.RUNNING)
            resolution = {
                "model_id": execution.provenance.get("model_id", request.model_id),
                "requested_skill": execution.provenance.get("requested_skill"),
                "resolved_skills": execution.provenance.get("resolved_skills", []),
                "primary_skill": execution.provenance.get("primary_skill"),
                "selection_source": execution.provenance.get(
                    "selection_source", "direct"
                ),
                "skill_snapshot": execution.provenance.get("skill_snapshot"),
                "model_snapshot": execution.provenance.get("model_snapshot", {}),
                "context_package_id": execution.provenance.get(
                    "context_package_id"
                ),
                "suggested_skill": execution.provenance.get("suggested_skill"),
                "confidence": execution.provenance.get("route_confidence", 1),
                "requires_confirmation": execution.provenance.get(
                    "route_requires_confirmation", False
                ),
                "reason_code": execution.provenance.get(
                    "route_reason_code", "pre_resolved"
                ),
            }
            await self._publish(execution, "run.resolved", resolution)
            await self._publish(
                execution,
                "run.resumed" if resume else "run.started",
                {
                    "status": RunStatus.RUNNING.value,
                    "service_version": self._service_version,
                    "agent_name": request.agent_name,
                    "graph_version": self._graph_version,
                    "agent_version": execution.provenance.get(
                        "agent_spec_hash",
                        "",
                    ),
                    "prompt_bundle_hash": execution.provenance.get(
                        "prompt_bundle_hash",
                        "",
                    ),
                    "model_profile": execution.provenance.get(
                        "model_profile",
                        "",
                    ),
                    "model_provider": execution.provenance.get(
                        "model_provider",
                        "",
                    ),
                    "model_name": execution.provenance.get(
                        "model_name",
                        getattr(self._runtime, "model_name", ""),
                    ),
                    "workflow_name": execution.provenance.get(
                        "workflow_name",
                        "",
                    ),
                    **resolution,
                    **(
                        {"lease_epoch": execution.lease.lease_epoch}
                        if resume
                        else {}
                    ),
                },
            )
            remaining_seconds = max(
                0.0,
                (
                    execution.deadline_at
                    - datetime.now(timezone.utc)
                ).total_seconds(),
            )
            if remaining_seconds <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining_seconds):
                stream_options = (
                    {
                        "lease": execution.lease,
                        "resume": resume,
                    }
                    if getattr(
                        self._runtime,
                        "supports_lease_context",
                        False,
                    )
                    else {}
                )
                async for event_type, data in self._runtime.stream(
                    request,
                    execution.cancel_event,
                    **stream_options,
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
        except LeaseLostError:
            execution.lease_lost = True
            execution.cancel_event.set()
        except TimeoutError:
            error = {
                "code": "runtime_deadline_exceeded",
                "stage": "runtime",
                "retryable": True,
            }
            await self._transition(
                execution,
                RunStatus.TIMED_OUT,
                error=error,
            )
            await self._publish(
                execution,
                "run.timed_out",
                {"status": RunStatus.TIMED_OUT.value, **error},
            )
        except asyncio.CancelledError:
            if execution.lease_lost or execution.abandoning:
                return
            if execution.status != RunStatus.CANCEL_REQUESTED:
                await self._transition(
                    execution,
                    RunStatus.CANCEL_REQUESTED,
                )
            await self._runtime.cancel(request.execution_id)
            await self._transition(execution, RunStatus.CANCELLED)
            await self._publish(
                execution,
                "run.cancelled",
                {"status": RunStatus.CANCELLED.value},
            )
        except Exception as exc:
            error = {
                "code": "agent_runtime_failed",
                "stage": "runtime",
                "retryable": False,
                "message": str(exc)[:1000],
            }
            await self._transition(
                execution,
                RunStatus.FAILED,
                error=error,
            )
            await self._publish(
                execution,
                "run.failed",
                {"status": RunStatus.FAILED.value, **error},
            )
        finally:
            if execution.renew_task is not None:
                execution.renew_task.cancel()
                await asyncio.gather(
                    execution.renew_task,
                    return_exceptions=True,
                )
            async with execution.condition:
                execution.condition.notify_all()

    async def _recover_or_fail_closed(
        self,
        execution: Execution,
    ) -> None:
        if not getattr(
            self._runtime,
            "supports_checkpoint_recovery",
            False,
        ):
            await self._fail_closed_recovery(execution)
            return
        try:
            can_resume = await self._runtime.can_resume(
                execution.request.execution_id
            )
        except Exception:
            can_resume = False
        if not can_resume:
            await self._fail_closed_recovery(execution)
            return
        await self._run(execution, resume=True)

    async def _fail_closed_recovery(
        self,
        execution: Execution,
    ) -> None:
        if execution.lease is None:
            return
        error = {
            "code": "runtime_recovery_unavailable",
            "stage": "runtime.recovery",
            "retryable": True,
        }
        try:
            await self._publish(
                execution,
                "runtime.recovery_failed",
                error,
            )
            await self._transition(
                execution,
                RunStatus.FAILED,
                error=error,
            )
            await self._publish(
                execution,
                "run.failed",
                {"status": RunStatus.FAILED.value, **error},
            )
        finally:
            async with execution.condition:
                execution.condition.notify_all()

    async def _renew_lease(self, execution: Execution) -> None:
        interval = max(1.0, self._lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            if execution.lease is None or execution.status.terminal:
                return
            try:
                execution.lease = await self._store.renew_lease(
                    execution.lease,
                    lease_seconds=self._lease_seconds,
                )
                record = await self._store.get_execution(
                    execution.request.execution_id
                )
                if (
                    record.status == RunStatus.CANCEL_REQUESTED
                    and execution.status
                    != RunStatus.CANCEL_REQUESTED
                ):
                    execution.status = RunStatus.CANCEL_REQUESTED
                    await self._publish(
                        execution,
                        "run.cancel_requested",
                        {
                            "status": (
                                RunStatus.CANCEL_REQUESTED.value
                            )
                        },
                    )
                    execution.cancel_event.set()
                    if (
                        execution.task is not None
                        and execution.task is not asyncio.current_task()
                        and not execution.task.done()
                    ):
                        execution.task.cancel()
                    return
            except LeaseLostError:
                execution.lease_lost = True
                execution.cancel_event.set()
                if (
                    execution.task is not None
                    and execution.task is not asyncio.current_task()
                    and not execution.task.done()
                ):
                    execution.task.cancel()
                return

    async def _transition(
        self,
        execution: Execution,
        target: RunStatus,
        *,
        error: dict | None = None,
    ) -> None:
        if execution.lease is None:
            raise LeaseLostError(execution.request.execution_id)
        record = await self._store.transition(
            execution.lease,
            target,
            error=error,
            retention_seconds=self._retention_seconds,
        )
        execution.status = record.status
        execution.expires_at = record.expires_at

    async def _publish(
        self,
        execution: Execution,
        event_type: str,
        data: dict | None = None,
    ) -> AgentEvent:
        if execution.lease is None:
            raise LeaseLostError(execution.request.execution_id)
        event = await self._store.append_event(
            execution.lease,
            event_type,
            data,
        )
        if self._notifier is not None:
            await self._notifier.publish_event(
                execution.request.execution_id,
                event.sequence,
            )
        async with execution.condition:
            execution.condition.notify_all()
        return event

    async def _purge_expired(self) -> None:
        await self._store.purge_expired()
        async with self._lock:
            local_execution_ids = tuple(self._executions)
        expired_local = []
        for execution_id in local_execution_ids:
            try:
                await self._store.get_execution(execution_id)
            except ExecutionNotFoundError:
                expired_local.append(execution_id)
        if expired_local:
            async with self._lock:
                for execution_id in expired_local:
                    execution = self._executions.pop(execution_id, None)
                    if (
                        execution is not None
                        and execution.signal_task is not None
                    ):
                        execution.signal_task.cancel()

    def _start_signal_listener(self, execution: Execution) -> None:
        if self._notifier is None or execution.signal_task is not None:
            return
        execution.signal_task = asyncio.create_task(
            self._listen_for_signals(execution),
            name=f"agent-signals:{execution.request.execution_id}",
        )

    async def _listen_for_signals(self, execution: Execution) -> None:
        assert self._notifier is not None
        try:
            async for signal in self._notifier.subscribe(
                execution.request.execution_id
            ):
                if signal.kind == "cancel":
                    record = await self._store.get_execution(
                        execution.request.execution_id
                    )
                    if (
                        record.status == RunStatus.CANCEL_REQUESTED
                        and execution.status
                        != RunStatus.CANCEL_REQUESTED
                    ):
                        execution.status = record.status
                        if execution.lease is not None:
                            await self._publish(
                                execution,
                                "run.cancel_requested",
                                {
                                    "status": (
                                        RunStatus.CANCEL_REQUESTED.value
                                    )
                                },
                            )
                        execution.cancel_event.set()
                        if (
                            execution.task is not None
                            and not execution.task.done()
                        ):
                            execution.task.cancel()
                async with execution.condition:
                    execution.condition.notify_all()
                if execution.status.terminal:
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            # The normal Store poll remains active when notifications fail.
            return

    async def close(self) -> None:
        async with self._lock:
            executions = list(self._executions.values())
        for execution in executions:
            execution.abandoning = True
        tasks = [
            task
            for execution in executions
            for task in (
                execution.task,
                execution.renew_task,
                execution.signal_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._notifier is not None:
            await self._notifier.close()

    @staticmethod
    def _request_with_provenance(request, provenance) -> AgentRunRequest:
        return request.model_copy(
            update={
                "requested_skill": provenance.get("requested_skill"),
                "resolved_skills": provenance.get("resolved_skills", []),
                "primary_skill": provenance.get("primary_skill"),
                "selection_source": provenance.get("selection_source"),
                "suggested_skill": provenance.get("suggested_skill"),
                "route_confidence": provenance.get("route_confidence"),
                "route_requires_confirmation": provenance.get(
                    "route_requires_confirmation", False
                ),
                "route_reason_code": provenance.get("route_reason_code"),
                "direct_capability": provenance.get("direct_capability"),
                "direct_capability_arguments": provenance.get(
                    "direct_capability_arguments", {}
                ),
                "context_package_id": provenance.get("context_package_id"),
            }
        )

    @staticmethod
    def _placeholder_request(record) -> AgentRunRequest:
        # Only identifiers are used by attached/replay handles. User content is
        # intentionally not duplicated in runtime_executions.
        return AgentRunRequest(
            execution_id=record.execution_id,
            run_id=record.run_id,
            request_id=record.request_id,
            idempotency_key=record.idempotency_key,
            conversation_id="runtime-replay",
            agent_name=record.agent_name,
            model_id=record.provenance.get("model_id", "auto"),
            requested_skill=record.provenance.get("requested_skill"),
            resolved_skills=record.provenance.get("resolved_skills", []),
            primary_skill=record.provenance.get("primary_skill"),
            selection_source=record.provenance.get("selection_source"),
            suggested_skill=record.provenance.get("suggested_skill"),
            route_confidence=record.provenance.get("route_confidence"),
            route_requires_confirmation=record.provenance.get(
                "route_requires_confirmation", False
            ),
            route_reason_code=record.provenance.get("route_reason_code"),
            direct_capability=record.provenance.get("direct_capability"),
            direct_capability_arguments=record.provenance.get(
                "direct_capability_arguments", {}
            ),
            context_package_id=record.provenance.get("context_package_id"),
            query="runtime replay",
            deadline_ms=max(
                1000,
                int(
                    (
                        record.deadline_at
                        - record.created_at
                    ).total_seconds()
                    * 1000
                ),
            ),
            shadow=record.shadow,
        )


__all__ = [
    "Execution",
    "ExecutionNotFoundError",
    "ExecutionRegistry",
    "IdempotencyConflictError",
]
