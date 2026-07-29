from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from app.observability import sanitize_event_data
from agent.artifacts import ArtifactRef, InlineArtifact

from .models import AgentEvent, AgentRunRequest, RunStatus, can_transition
from .store import (
    ExecutionNotFoundError,
    IdempotencyConflictError,
    LeaseLostError,
    LeaseToken,
    StartDisposition,
    StartResult,
    StoredExecution,
    request_fingerprint,
)


_TERMINAL_STATUS_VALUES = tuple(
    status.value for status in RunStatus if status.terminal
)


def configure_psycopg_event_loop_policy() -> None:
    """Use the selector loop required by psycopg async connections on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )


configure_psycopg_event_loop_policy()


def _record_from_row(row: dict[str, Any]) -> StoredExecution:
    return StoredExecution(
        execution_id=row["execution_id"],
        run_id=row["run_id"],
        request_id=row["request_id"],
        idempotency_key=row["idempotency_key"],
        request_hash=row["request_hash"],
        protocol_version=row["protocol_version"],
        status=RunStatus(row["status"]),
        owner_id=row["owner_id"],
        lease_epoch=row["lease_epoch"],
        lease_expires_at=row["lease_expires_at"],
        last_sequence=row["last_sequence"],
        deadline_at=row["deadline_at"],
        agent_name=row["agent_name"],
        workflow_name=row["workflow_name"],
        graph_version=row["graph_version"],
        service_version=row["service_version"],
        shadow=row["shadow"],
        error=row["error"],
        provenance=row["provenance"] or {},
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        expires_at=row["expires_at"],
        updated_at=row["updated_at"],
    )


class PostgresRuntimeStore:
    """Fenced PostgreSQL source of truth for executions and Runtime Outbox."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def open(
        cls,
        connection_string: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
    ) -> "PostgresRuntimeStore":
        if not connection_string:
            raise ValueError("runtime PostgreSQL connection string is required")
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=connection_string,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={
                # Required by AsyncPostgresSaver.setup(), which creates
                # concurrent indexes. RuntimeStore mutations that need
                # atomicity still open explicit transactions.
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                "options": "-c search_path=agent_runtime",
            },
        )
        await pool.open(wait=True)
        return cls(pool)

    async def build_checkpointer(
        self,
        *,
        setup: bool,
    ):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from .checkpointer import FencedAsyncCheckpointer

        delegate = AsyncPostgresSaver(self._pool)
        if setup:
            await delegate.setup()
        return FencedAsyncCheckpointer(delegate, self)

    async def assert_lease(self, lease: LeaseToken) -> None:
        async with self.hold_lease(lease):
            return

    async def stage_artifact(
        self,
        lease: LeaseToken,
        artifact: InlineArtifact,
    ) -> None:
        validated = InlineArtifact.model_validate(artifact)
        encoded = validated.content.encode("utf-8")
        actual_hash = hashlib.sha256(encoded).hexdigest()
        if (
            actual_hash != validated.ref.content_hash
            or len(encoded) != validated.ref.size_bytes
        ):
            raise ValueError("artifact content does not match its reference")
        async with self._pool.connection() as connection:
            async with connection.transaction():
                execution = await self._locked_execution(connection, lease)
                cursor = await connection.execute(
                    """
                    INSERT INTO agent_runtime.runtime_artifacts (
                        execution_id,
                        artifact_id,
                        lease_epoch,
                        artifact_type,
                        schema_version,
                        content_hash,
                        media_type,
                        size_bytes,
                        storage_kind,
                        inline_content,
                        metadata,
                        expires_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        'inline', %s, %s::jsonb, %s
                    )
                    ON CONFLICT (execution_id, artifact_id)
                    DO NOTHING
                    RETURNING content_hash
                    """,
                    (
                        lease.execution_id,
                        validated.ref.artifact_id,
                        lease.lease_epoch,
                        validated.ref.artifact_type,
                        validated.ref.schema_version,
                        validated.ref.content_hash,
                        validated.ref.media_type,
                        validated.ref.size_bytes,
                        encoded,
                        json.dumps(
                            validated.metadata,
                            ensure_ascii=False,
                        ),
                        execution.expires_at,
                    ),
                )
                inserted = await cursor.fetchone()
                if inserted is None:
                    cursor = await connection.execute(
                        """
                        SELECT content_hash
                        FROM agent_runtime.runtime_artifacts
                        WHERE execution_id = %s
                            AND artifact_id = %s
                        """,
                        (
                            lease.execution_id,
                            validated.ref.artifact_id,
                        ),
                    )
                    existing = await cursor.fetchone()
                    if (
                        existing is None
                        or existing["content_hash"]
                        != validated.ref.content_hash
                    ):
                        raise RuntimeError("artifact id collision")

    async def get_artifact(
        self,
        execution_id: str,
        artifact_id: str,
    ) -> InlineArtifact:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    artifact_id,
                    artifact_type,
                    schema_version,
                    content_hash,
                    media_type,
                    size_bytes,
                    inline_content,
                    metadata
                FROM agent_runtime.runtime_artifacts
                WHERE execution_id = %s
                    AND artifact_id = %s
                    AND storage_kind = 'inline'
                """,
                (execution_id, artifact_id),
            )
            row = await cursor.fetchone()
        if row is None:
            raise LookupError(artifact_id)
        return InlineArtifact(
            ref=ArtifactRef(
                artifact_id=row["artifact_id"],
                artifact_type=row["artifact_type"],
                schema_version=row["schema_version"],
                content_hash=row["content_hash"],
                media_type=row["media_type"],
                size_bytes=row["size_bytes"],
            ),
            content=bytes(row["inline_content"]).decode("utf-8"),
            metadata=row["metadata"] or {},
        )

    async def close(self) -> None:
        await self._pool.close()

    async def validate_ready(self) -> dict:
        required = (
            "agent_runtime.runtime_executions",
            "agent_runtime.runtime_events",
            "agent_runtime.runtime_artifacts",
        )
        checkpoint_tables = (
            "agent_runtime.checkpoint_migrations",
            "agent_runtime.checkpoints",
            "agent_runtime.checkpoint_blobs",
            "agent_runtime.checkpoint_writes",
        )
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    to_regclass(%s) AS executions,
                    to_regclass(%s) AS events,
                    to_regclass(%s) AS artifacts,
                    to_regclass(%s) AS checkpoint_migrations,
                    to_regclass(%s) AS checkpoints,
                    to_regclass(%s) AS checkpoint_blobs,
                    to_regclass(%s) AS checkpoint_writes
                """,
                (*required, *checkpoint_tables),
            )
            row = await cursor.fetchone()
        values = list(row.values())
        missing = [
            name
            for name, value in zip(required, values[:3], strict=True)
            if value is None
        ]
        if missing:
            raise RuntimeError(
                f"agent runtime schema is missing tables: {missing}"
            )
        return {
            "kind": "postgres",
            "durable": True,
            "cross_process_replay": True,
            "checkpoint_ready": all(
                value is not None for value in values[3:]
            ),
        }

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
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        fingerprint = request_fingerprint(request)
        deadline_at = datetime.now(timezone.utc) + timedelta(
            milliseconds=request.deadline_ms
        )
        async with self._pool.connection() as connection:
            async with connection.transaction():
                cursor = await connection.execute(
                    """
                    INSERT INTO agent_runtime.runtime_executions (
                        execution_id,
                        run_id,
                        request_id,
                        idempotency_key,
                        request_hash,
                        protocol_version,
                        status,
                        owner_id,
                        lease_epoch,
                        lease_expires_at,
                        deadline_at,
                        agent_name,
                        workflow_name,
                        graph_version,
                        service_version,
                        shadow,
                        provenance,
                        expires_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, 'queued', %s, 1,
                        NOW() + (%s * INTERVAL '1 second'),
                        %s, %s, %s, %s, %s, %s, %s::jsonb,
                        NOW() + (%s * INTERVAL '1 second')
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING *
                    """,
                    (
                        request.execution_id,
                        request.run_id,
                        request.request_id,
                        request.idempotency_key,
                        fingerprint,
                        request.protocol_version,
                        owner_id,
                        lease_seconds,
                        deadline_at,
                        request.agent_name,
                        (provenance or {}).get("workflow_name"),
                        graph_version,
                        service_version,
                        request.shadow,
                        json.dumps(provenance or {}, ensure_ascii=False),
                        retention_seconds,
                    ),
                )
                inserted = await cursor.fetchone()
                if inserted is not None:
                    execution = _record_from_row(inserted)
                    return StartResult(
                        execution=execution,
                        disposition=StartDisposition.CREATED,
                        lease=self._lease_from(execution),
                    )

                cursor = await connection.execute(
                    """
                    SELECT *,
                        lease_expires_at > NOW() AS lease_valid
                    FROM agent_runtime.runtime_executions
                    WHERE execution_id = %s
                    FOR UPDATE
                    """,
                    (request.execution_id,),
                )
                existing_row = await cursor.fetchone()
                if existing_row is None:
                    # A different execution already owns run_id or
                    # idempotency_key.
                    raise IdempotencyConflictError(request.execution_id)
                existing = _record_from_row(existing_row)
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
                if existing_row["lease_valid"]:
                    if existing.owner_id != owner_id:
                        return StartResult(
                            execution=existing,
                            disposition=StartDisposition.ATTACHED,
                            lease=None,
                        )
                    cursor = await connection.execute(
                        """
                        UPDATE agent_runtime.runtime_executions
                        SET lease_expires_at =
                                NOW() + (%s * INTERVAL '1 second'),
                            updated_at = NOW()
                        WHERE execution_id = %s
                        RETURNING *
                        """,
                        (lease_seconds, request.execution_id),
                    )
                    renewed = _record_from_row(await cursor.fetchone())
                    return StartResult(
                        execution=renewed,
                        disposition=StartDisposition.OWNED,
                        lease=self._lease_from(renewed),
                    )

                cursor = await connection.execute(
                    """
                    UPDATE agent_runtime.runtime_executions
                    SET owner_id = %s,
                        lease_epoch = lease_epoch + 1,
                        lease_expires_at =
                            NOW() + (%s * INTERVAL '1 second'),
                        updated_at = NOW()
                    WHERE execution_id = %s
                    RETURNING *
                    """,
                    (owner_id, lease_seconds, request.execution_id),
                )
                taken_over = _record_from_row(await cursor.fetchone())
                return StartResult(
                    execution=taken_over,
                    disposition=StartDisposition.TAKEOVER,
                    lease=self._lease_from(taken_over),
                )

    async def renew_lease(
        self,
        lease: LeaseToken,
        *,
        lease_seconds: int,
    ) -> LeaseToken:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE agent_runtime.runtime_executions
                SET lease_expires_at =
                        NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE execution_id = %s
                    AND owner_id = %s
                    AND lease_epoch = %s
                    AND lease_expires_at > NOW()
                    AND status IN (
                        'queued',
                        'running',
                        'cancel_requested'
                    )
                RETURNING *
                """,
                (
                    lease_seconds,
                    lease.execution_id,
                    lease.owner_id,
                    lease.lease_epoch,
                ),
            )
            row = await cursor.fetchone()
        if row is None:
            raise LeaseLostError(lease.execution_id)
        return self._lease_from(_record_from_row(row))

    async def get_execution(
        self,
        execution_id: str,
    ) -> StoredExecution:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT *
                FROM agent_runtime.runtime_executions
                WHERE execution_id = %s
                """,
                (execution_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ExecutionNotFoundError(execution_id)
        return _record_from_row(row)

    async def transition(
        self,
        lease: LeaseToken,
        target: RunStatus,
        *,
        error: dict | None = None,
        retention_seconds: int,
    ) -> StoredExecution:
        async with self._pool.connection() as connection:
            async with connection.transaction():
                execution = await self._locked_execution(connection, lease)
                if not can_transition(execution.status, target):
                    raise RuntimeError(
                        "invalid run transition "
                        f"{execution.status.value} -> {target.value}"
                    )
                terminal = target.terminal
                cursor = await connection.execute(
                    """
                    UPDATE agent_runtime.runtime_executions
                    SET status = %s,
                        error = %s::jsonb,
                        started_at = CASE
                            WHEN %s = 'running'
                                THEN COALESCE(started_at, NOW())
                            ELSE started_at
                        END,
                        completed_at = CASE
                            WHEN %s THEN NOW()
                            ELSE completed_at
                        END,
                        expires_at = CASE
                            WHEN %s
                                THEN NOW() + (%s * INTERVAL '1 second')
                            ELSE expires_at
                        END,
                        updated_at = NOW()
                    WHERE execution_id = %s
                    RETURNING *
                    """,
                    (
                        target.value,
                        (
                            json.dumps(error, ensure_ascii=False)
                            if error is not None
                            else None
                        ),
                        target.value,
                        terminal,
                        terminal,
                        retention_seconds,
                        lease.execution_id,
                    ),
                )
                return _record_from_row(await cursor.fetchone())

    async def request_cancel(
        self,
        execution_id: str,
    ) -> StoredExecution:
        async with self._pool.connection() as connection:
            async with connection.transaction():
                cursor = await connection.execute(
                    """
                    SELECT *
                    FROM agent_runtime.runtime_executions
                    WHERE execution_id = %s
                    FOR UPDATE
                    """,
                    (execution_id,),
                )
                row = await cursor.fetchone()
                if row is None:
                    raise ExecutionNotFoundError(execution_id)
                execution = _record_from_row(row)
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
                cursor = await connection.execute(
                    """
                    UPDATE agent_runtime.runtime_executions
                    SET status = 'cancel_requested',
                        updated_at = NOW()
                    WHERE execution_id = %s
                    RETURNING *
                    """,
                    (execution_id,),
                )
                return _record_from_row(await cursor.fetchone())

    async def append_event(
        self,
        lease: LeaseToken,
        event_type: str,
        data: dict | None = None,
    ) -> AgentEvent:
        async with self._pool.connection() as connection:
            async with connection.transaction():
                execution = await self._locked_execution(connection, lease)
                event = AgentEvent.create(
                    execution_id=execution.execution_id,
                    run_id=execution.run_id,
                    sequence=execution.last_sequence + 1,
                    event_type=event_type,
                    data=sanitize_event_data(data or {}),
                )
                await connection.execute(
                    """
                    INSERT INTO agent_runtime.runtime_events (
                        execution_id,
                        sequence,
                        lease_epoch,
                        run_id,
                        event_type,
                        occurred_at,
                        trace_id,
                        span_id,
                        parent_span_id,
                        category,
                        stage,
                        event_schema_version,
                        content_capture_level,
                        data
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb
                    )
                    """,
                    (
                        event.execution_id,
                        event.sequence,
                        lease.lease_epoch,
                        event.run_id,
                        event.type,
                        event.occurred_at,
                        event.trace_id,
                        event.span_id,
                        event.parent_span_id,
                        event.category,
                        event.stage,
                        event.event_schema_version,
                        event.content_capture_level,
                        json.dumps(event.data, ensure_ascii=False),
                    ),
                )
                await connection.execute(
                    """
                    UPDATE agent_runtime.runtime_executions
                    SET last_sequence = %s,
                        updated_at = NOW()
                    WHERE execution_id = %s
                    """,
                    (event.sequence, execution.execution_id),
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
        if not await self._exists(execution_id):
            raise ExecutionNotFoundError(execution_id)
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    execution_id,
                    run_id,
                    sequence,
                    event_type,
                    occurred_at,
                    trace_id,
                    span_id,
                    parent_span_id,
                    category,
                    stage,
                    event_schema_version,
                    content_capture_level,
                    data
                FROM agent_runtime.runtime_events
                WHERE execution_id = %s
                    AND sequence > %s
                ORDER BY sequence
                LIMIT %s
                """,
                (execution_id, max(0, sequence), limit),
            )
            rows = await cursor.fetchall()
        return [
            AgentEvent(
                execution_id=row["execution_id"],
                run_id=row["run_id"],
                sequence=row["sequence"],
                type=row["event_type"],
                occurred_at=row["occurred_at"],
                trace_id=row["trace_id"],
                span_id=row["span_id"],
                parent_span_id=row["parent_span_id"],
                category=row["category"],
                stage=row["stage"],
                event_schema_version=row["event_schema_version"],
                content_capture_level=row["content_capture_level"],
                data=row["data"] or {},
            )
            for row in rows
        ]

    async def purge_expired(self) -> int:
        async with self._pool.connection() as connection:
            async with connection.transaction():
                cursor = await connection.execute(
                    """
                    SELECT execution_id
                    FROM agent_runtime.runtime_executions
                    WHERE status = ANY(%s)
                        AND expires_at <= NOW()
                    ORDER BY expires_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 500
                    """,
                    (list(_TERMINAL_STATUS_VALUES),),
                )
                execution_ids = [
                    row["execution_id"] for row in await cursor.fetchall()
                ]
                if not execution_ids:
                    return 0
                cursor = await connection.execute(
                    """
                    SELECT to_regclass(
                        'agent_runtime.checkpoint_writes'
                    ) IS NOT NULL AS checkpoint_ready
                    """
                )
                checkpoint_ready = bool(
                    (await cursor.fetchone())["checkpoint_ready"]
                )
                if checkpoint_ready:
                    for table in (
                        "checkpoint_writes",
                        "checkpoint_blobs",
                        "checkpoints",
                    ):
                        await connection.execute(
                            f"""
                            DELETE FROM agent_runtime.{table}
                            WHERE thread_id = ANY(%s)
                            """,
                            (execution_ids,),
                        )
                await connection.execute(
                    """
                    DELETE FROM agent_runtime.runtime_executions
                    WHERE execution_id = ANY(%s)
                    """,
                    (execution_ids,),
                )
                return len(execution_ids)

    @asynccontextmanager
    async def hold_lease(self, lease: LeaseToken):
        """Hold the execution row lock for one fenced checkpoint operation."""
        async with self._pool.connection() as connection:
            async with connection.transaction():
                await self._locked_execution(connection, lease)
                yield

    async def _exists(self, execution_id: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM agent_runtime.runtime_executions
                    WHERE execution_id = %s
                ) AS present
                """,
                (execution_id,),
            )
            row = await cursor.fetchone()
        return bool(row["present"])

    async def _locked_execution(
        self,
        connection: Any,
        lease: LeaseToken,
    ) -> StoredExecution:
        cursor = await connection.execute(
            """
            SELECT *
            FROM agent_runtime.runtime_executions
            WHERE execution_id = %s
                AND owner_id = %s
                AND lease_epoch = %s
                AND lease_expires_at > NOW()
            FOR UPDATE
            """,
            (
                lease.execution_id,
                lease.owner_id,
                lease.lease_epoch,
            ),
        )
        row = await cursor.fetchone()
        if row is None:
            raise LeaseLostError(lease.execution_id)
        return _record_from_row(row)

    @staticmethod
    def _lease_from(execution: StoredExecution) -> LeaseToken:
        if (
            execution.owner_id is None
            or execution.lease_expires_at is None
            or execution.lease_epoch <= 0
        ):
            raise RuntimeError("execution does not have a valid lease shape")
        return LeaseToken(
            execution_id=execution.execution_id,
            owner_id=execution.owner_id,
            lease_epoch=execution.lease_epoch,
            lease_expires_at=execution.lease_expires_at,
        )
