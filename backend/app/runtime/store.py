from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Protocol

from app.observability import sanitize_event_data
from agent.context import RuntimeLease
from agent.artifacts import InlineArtifact

from .models import (
    AgentEvent,
    AgentRunRequest,
    RunSnapshot,
    RunStatus,
    can_transition,
)


class IdempotencyConflictError(RuntimeError):
    pass


class ExecutionNotFoundError(LookupError):
    pass


class LeaseUnavailableError(RuntimeError):
    pass


class LeaseLostError(RuntimeError):
    pass


class StartDisposition(StrEnum):
    CREATED = "created"
    OWNED = "owned"
    ATTACHED = "attached"
    TAKEOVER = "takeover"
    TERMINAL_REPLAY = "terminal_replay"


LeaseToken = RuntimeLease


@dataclass(frozen=True)
class StoredExecution:
    execution_id: str
    run_id: str
    request_id: str
    idempotency_key: str
    request_hash: str
    protocol_version: int
    status: RunStatus
    owner_id: str | None
    lease_epoch: int
    lease_expires_at: datetime | None
    last_sequence: int
    deadline_at: datetime
    agent_name: str
    workflow_name: str | None
    graph_version: str
    service_version: str
    shadow: bool
    error: dict | None
    provenance: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    updated_at: datetime

    def snapshot(self) -> RunSnapshot:
        return RunSnapshot(
            service_version=self.service_version,
            execution_id=self.execution_id,
            run_id=self.run_id,
            status=self.status,
            last_sequence=self.last_sequence,
            started_at=self.started_at,
            completed_at=self.completed_at,
            expires_at=self.expires_at,
            error=self.error,
        )


@dataclass(frozen=True)
class StartResult:
    execution: StoredExecution
    disposition: StartDisposition
    lease: LeaseToken | None


def request_fingerprint(request: AgentRunRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RuntimeStore(Protocol):
    async def validate_ready(self) -> dict: ...

    async def assert_lease(self, lease: LeaseToken) -> None: ...

    async def stage_artifact(
        self,
        lease: LeaseToken,
        artifact: InlineArtifact,
    ) -> None: ...

    async def get_artifact(
        self,
        execution_id: str,
        artifact_id: str,
    ) -> InlineArtifact: ...

    async def start_execution(
        self,
        request: AgentRunRequest,
        *,
        owner_id: str,
        service_version: str,
        graph_version: str,
        lease_seconds: int,
        retention_seconds: int,
        provenance: dict | None = None,
    ) -> StartResult: ...

    async def renew_lease(
        self,
        lease: LeaseToken,
        *,
        lease_seconds: int,
    ) -> LeaseToken: ...

    async def get_execution(
        self,
        execution_id: str,
    ) -> StoredExecution: ...

    async def transition(
        self,
        lease: LeaseToken,
        target: RunStatus,
        *,
        error: dict | None = None,
        retention_seconds: int,
    ) -> StoredExecution: ...

    async def request_cancel(
        self,
        execution_id: str,
    ) -> StoredExecution: ...

    async def append_event(
        self,
        lease: LeaseToken,
        event_type: str,
        data: dict | None = None,
    ) -> AgentEvent: ...

    async def events_after(
        self,
        execution_id: str,
        sequence: int,
        *,
        limit: int = 256,
    ) -> list[AgentEvent]: ...

    async def purge_expired(self) -> int: ...


class InMemoryRuntimeStore:
    """Contract-compatible test/local store; PostgreSQL is the Phase 4 target."""

    def __init__(self) -> None:
        self._executions: dict[str, StoredExecution] = {}
        self._events: dict[str, list[AgentEvent]] = {}
        self._artifacts: dict[
            tuple[str, str],
            InlineArtifact,
        ] = {}
        self._lock = asyncio.Lock()

    async def validate_ready(self) -> dict:
        return {
            "kind": "memory",
            "durable": False,
            "cross_process_replay": False,
        }

    async def assert_lease(self, lease: LeaseToken) -> None:
        async with self._lock:
            self._require_lease(
                lease,
                now=datetime.now(timezone.utc),
            )

    async def stage_artifact(
        self,
        lease: LeaseToken,
        artifact: InlineArtifact,
    ) -> None:
        validated = InlineArtifact.model_validate(artifact)
        encoded = validated.content.encode("utf-8")
        if (
            hashlib.sha256(encoded).hexdigest()
            != validated.ref.content_hash
            or len(encoded) != validated.ref.size_bytes
        ):
            raise ValueError("artifact content does not match its reference")
        async with self._lock:
            self._require_lease(
                lease,
                now=datetime.now(timezone.utc),
            )
            key = (lease.execution_id, validated.ref.artifact_id)
            existing = self._artifacts.get(key)
            if (
                existing is not None
                and existing.ref.content_hash
                != validated.ref.content_hash
            ):
                raise RuntimeError("artifact id collision")
            self._artifacts[key] = validated

    async def get_artifact(
        self,
        execution_id: str,
        artifact_id: str,
    ) -> InlineArtifact:
        async with self._lock:
            artifact = self._artifacts.get(
                (execution_id, artifact_id)
            )
        if artifact is None:
            raise LookupError(artifact_id)
        return artifact

    async def start_execution(
        self,
        request: AgentRunRequest,
        *,
        owner_id: str,
        service_version: str,
        graph_version: str,
        lease_seconds: int,
        retention_seconds: int,
        provenance: dict | None = None,
    ) -> StartResult:
        now = datetime.now(timezone.utc)
        fingerprint = request_fingerprint(request)
        async with self._lock:
            existing = self._executions.get(request.execution_id)
            if existing is None:
                lease = LeaseToken(
                    execution_id=request.execution_id,
                    owner_id=owner_id,
                    lease_epoch=1,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                execution = StoredExecution(
                    execution_id=request.execution_id,
                    run_id=request.run_id,
                    request_id=request.request_id,
                    idempotency_key=request.idempotency_key,
                    request_hash=fingerprint,
                    protocol_version=request.protocol_version,
                    status=RunStatus.QUEUED,
                    owner_id=owner_id,
                    lease_epoch=lease.lease_epoch,
                    lease_expires_at=lease.lease_expires_at,
                    last_sequence=0,
                    deadline_at=now
                    + timedelta(milliseconds=request.deadline_ms),
                    agent_name=request.agent_name,
                    workflow_name=(provenance or {}).get("workflow_name"),
                    graph_version=graph_version,
                    service_version=service_version,
                    shadow=request.shadow,
                    error=None,
                    provenance=dict(provenance or {}),
                    created_at=now,
                    started_at=None,
                    completed_at=None,
                    expires_at=now + timedelta(seconds=retention_seconds),
                    updated_at=now,
                )
                self._executions[request.execution_id] = execution
                self._events[request.execution_id] = []
                return StartResult(
                    execution=execution,
                    disposition=StartDisposition.CREATED,
                    lease=lease,
                )

            if (
                existing.request_hash != fingerprint
                or existing.run_id != request.run_id
                or existing.idempotency_key != request.idempotency_key
            ):
                raise IdempotencyConflictError(request.execution_id)
            if existing.status.terminal:
                return StartResult(
                    execution=existing,
                    disposition=StartDisposition.TERMINAL_REPLAY,
                    lease=None,
                )
            if (
                existing.lease_expires_at is not None
                and existing.lease_expires_at > now
            ):
                if existing.owner_id != owner_id:
                    return StartResult(
                        execution=existing,
                        disposition=StartDisposition.ATTACHED,
                        lease=None,
                    )
                lease = LeaseToken(
                    execution_id=existing.execution_id,
                    owner_id=owner_id,
                    lease_epoch=existing.lease_epoch,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                )
                renewed = replace(
                    existing,
                    lease_expires_at=lease.lease_expires_at,
                    updated_at=now,
                )
                self._executions[existing.execution_id] = renewed
                return StartResult(
                    execution=renewed,
                    disposition=StartDisposition.OWNED,
                    lease=lease,
                )

            lease = LeaseToken(
                execution_id=existing.execution_id,
                owner_id=owner_id,
                lease_epoch=existing.lease_epoch + 1,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            taken_over = replace(
                existing,
                owner_id=owner_id,
                lease_epoch=lease.lease_epoch,
                lease_expires_at=lease.lease_expires_at,
                updated_at=now,
            )
            self._executions[existing.execution_id] = taken_over
            return StartResult(
                execution=taken_over,
                disposition=StartDisposition.TAKEOVER,
                lease=lease,
            )

    async def renew_lease(
        self,
        lease: LeaseToken,
        *,
        lease_seconds: int,
    ) -> LeaseToken:
        now = datetime.now(timezone.utc)
        async with self._lock:
            execution = self._require_lease(lease, now=now)
            renewed = LeaseToken(
                execution_id=lease.execution_id,
                owner_id=lease.owner_id,
                lease_epoch=lease.lease_epoch,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            self._executions[lease.execution_id] = replace(
                execution,
                lease_expires_at=renewed.lease_expires_at,
                updated_at=now,
            )
            return renewed

    async def get_execution(
        self,
        execution_id: str,
    ) -> StoredExecution:
        async with self._lock:
            execution = self._executions.get(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        return execution

    async def transition(
        self,
        lease: LeaseToken,
        target: RunStatus,
        *,
        error: dict | None = None,
        retention_seconds: int,
    ) -> StoredExecution:
        now = datetime.now(timezone.utc)
        async with self._lock:
            execution = self._require_lease(lease, now=now)
            if not can_transition(execution.status, target):
                raise RuntimeError(
                    "invalid run transition "
                    f"{execution.status.value} -> {target.value}"
                )
            started_at = execution.started_at
            completed_at = execution.completed_at
            expires_at = execution.expires_at
            if target == RunStatus.RUNNING and started_at is None:
                started_at = now
            if target.terminal:
                completed_at = now
                expires_at = now + timedelta(seconds=retention_seconds)
            updated = replace(
                execution,
                status=target,
                error=error,
                started_at=started_at,
                completed_at=completed_at,
                expires_at=expires_at,
                updated_at=now,
            )
            self._executions[lease.execution_id] = updated
            return updated

    async def request_cancel(
        self,
        execution_id: str,
    ) -> StoredExecution:
        now = datetime.now(timezone.utc)
        async with self._lock:
            execution = self._executions.get(execution_id)
            if execution is None:
                raise ExecutionNotFoundError(execution_id)
            if execution.status.terminal:
                return execution
            if not can_transition(
                execution.status,
                RunStatus.CANCEL_REQUESTED,
            ):
                raise RuntimeError(
                    "invalid run transition "
                    f"{execution.status.value} -> cancel_requested"
                )
            updated = replace(
                execution,
                status=RunStatus.CANCEL_REQUESTED,
                updated_at=now,
            )
            self._executions[execution_id] = updated
            return updated

    async def append_event(
        self,
        lease: LeaseToken,
        event_type: str,
        data: dict | None = None,
    ) -> AgentEvent:
        now = datetime.now(timezone.utc)
        async with self._lock:
            execution = self._require_lease(lease, now=now)
            event = AgentEvent.create(
                execution_id=execution.execution_id,
                run_id=execution.run_id,
                sequence=execution.last_sequence + 1,
                event_type=event_type,
                data=sanitize_event_data(data or {}),
            )
            self._events[execution.execution_id].append(event)
            self._executions[execution.execution_id] = replace(
                execution,
                last_sequence=event.sequence,
                updated_at=now,
            )
            return event

    async def events_after(
        self,
        execution_id: str,
        sequence: int,
        *,
        limit: int = 256,
    ) -> list[AgentEvent]:
        if limit <= 0:
            return []
        async with self._lock:
            if execution_id not in self._executions:
                raise ExecutionNotFoundError(execution_id)
            return [
                event
                for event in self._events[execution_id]
                if event.sequence > max(0, sequence)
            ][:limit]

    async def purge_expired(self) -> int:
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [
                execution_id
                for execution_id, execution in self._executions.items()
                if execution.status.terminal and execution.expires_at <= now
            ]
            for execution_id in expired:
                self._executions.pop(execution_id, None)
                self._events.pop(execution_id, None)
                for key in [
                    key
                    for key in self._artifacts
                    if key[0] == execution_id
                ]:
                    self._artifacts.pop(key, None)
            return len(expired)

    def _require_lease(
        self,
        lease: LeaseToken,
        *,
        now: datetime,
    ) -> StoredExecution:
        execution = self._executions.get(lease.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(lease.execution_id)
        if (
            execution.owner_id != lease.owner_id
            or execution.lease_epoch != lease.lease_epoch
            or execution.lease_expires_at is None
            or execution.lease_expires_at <= now
        ):
            raise LeaseLostError(lease.execution_id)
        return execution
