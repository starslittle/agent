from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from agent.artifacts import create_inline_artifact
from agent.context import RUNTIME_LEASE_KEY
from app.runtime.models import AgentRunRequest, RunStatus
from app.runtime.postgres_store import PostgresRuntimeStore
from app.runtime.store import (
    ExecutionNotFoundError,
    LeaseLostError,
    StartDisposition,
)


pytestmark = pytest.mark.asyncio


def runtime_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "")
    if not value:
        pytest.skip("TEST_DATABASE_URL is not configured")
    return value


async def test_postgres_runtime_outbox_and_lease_fencing():
    connection_string = runtime_database_url()
    store = await PostgresRuntimeStore.open(connection_string)
    execution_id = f"exec-pg-{uuid.uuid4().hex}"
    request = AgentRunRequest(
        execution_id=execution_id,
        run_id=f"run-pg-{uuid.uuid4().hex}",
        request_id=f"request-pg-{uuid.uuid4().hex}",
        idempotency_key=f"idem-pg-{uuid.uuid4().hex}",
        conversation_id=f"conversation-pg-{uuid.uuid4().hex}",
        query="验证 PostgreSQL Runtime Store",
    )
    checkpointer = None
    try:
        checkpointer = await store.build_checkpointer(setup=True)
        readiness = await store.validate_ready()
        assert readiness["cross_process_replay"] is True
        assert readiness["checkpoint_ready"] is True

        created = await store.start_execution(
            request,
            owner_id="integration-worker-a",
            service_version="integration-test",
            graph_version="qidian-root-v1",
            lease_seconds=1,
            retention_seconds=300,
        )
        assert created.disposition == StartDisposition.CREATED
        assert created.lease is not None
        old_lease = created.lease

        class CheckpointState(TypedDict):
            value: int

        checkpoint_graph = StateGraph(CheckpointState)
        checkpoint_graph.add_node(
            "increment",
            lambda state: {"value": state["value"] + 1},
        )
        checkpoint_graph.add_edge(START, "increment")
        checkpoint_graph.add_edge("increment", END)
        compiled = checkpoint_graph.compile(checkpointer=checkpointer)
        checkpoint_config = {
            "configurable": {
                "thread_id": execution_id,
                "checkpoint_ns": "",
                RUNTIME_LEASE_KEY: old_lease,
            }
        }
        result = await compiled.ainvoke(
            {"value": 1},
            checkpoint_config,
        )
        assert result == {"value": 2}

        await store.transition(
            old_lease,
            RunStatus.RUNNING,
            retention_seconds=300,
        )
        artifact = create_inline_artifact(
            artifact_type="integration_evidence",
            content='{"verified":true}',
        )
        await store.stage_artifact(old_lease, artifact)
        restored_artifact = await store.get_artifact(
            execution_id,
            artifact.ref.artifact_id,
        )
        assert restored_artifact == artifact
        first = await store.append_event(
            old_lease,
            "run.started",
            {"status": "running"},
        )
        second = await store.append_event(
            old_lease,
            "answer.delta",
            {"text": "持久事件"},
        )
        assert (first.sequence, second.sequence) == (1, 2)

        other_store = await PostgresRuntimeStore.open(connection_string)
        try:
            replayed = await other_store.events_after(execution_id, 1)
            assert [event.sequence for event in replayed] == [2]
            assert replayed[0].data == {"text": "持久事件"}

            await asyncio.sleep(1.1)
            takeover = await other_store.start_execution(
                request,
                owner_id="integration-worker-b",
                service_version="integration-test",
                graph_version="qidian-root-v1",
                lease_seconds=30,
                retention_seconds=300,
            )
            assert takeover.disposition == StartDisposition.TAKEOVER
            assert takeover.lease is not None
            assert takeover.lease.lease_epoch == old_lease.lease_epoch + 1

            with pytest.raises(LeaseLostError):
                await store.append_event(
                    old_lease,
                    "answer.delta",
                    {"text": "旧 owner 不得写入"},
                )
            fenced_event = await other_store.append_event(
                takeover.lease,
                "progress",
                {"stage": "runtime.recovery"},
            )
            assert fenced_event.sequence == 3
            await other_store.transition(
                takeover.lease,
                RunStatus.FAILED,
                error={"code": "integration_cleanup"},
                retention_seconds=0,
            )
            assert await other_store.purge_expired() == 1
            with pytest.raises(ExecutionNotFoundError):
                await other_store.get_execution(execution_id)
            assert await checkpointer.aget_tuple(
                {
                    "configurable": {
                        "thread_id": execution_id,
                        "checkpoint_ns": "",
                    }
                }
            ) is None
        finally:
            await other_store.close()
    finally:
        if checkpointer is not None:
            await checkpointer.adelete_thread(execution_id)
        async with store._pool.connection() as connection:
            await connection.execute(
                """
                DELETE FROM agent_runtime.runtime_executions
                WHERE execution_id = %s
                """,
                (execution_id,),
            )
        await store.close()


async def test_real_process_kill_is_resumed_by_a_second_owner():
    connection_string = runtime_database_url()
    execution_id = f"exec-crash-{uuid.uuid4().hex}"
    backend_root = Path(__file__).resolve().parents[2]
    worker_module = "tests.integration.runtime_crash_worker"
    store = await PostgresRuntimeStore.open(connection_string)
    checkpointer = await store.build_checkpointer(setup=True)
    first = None
    with tempfile.TemporaryDirectory() as temporary_directory:
        marker = str(Path(temporary_directory) / "model-entered")
        base_environment = {
            **os.environ,
            "PYTHONPATH": str(backend_root),
            "TEST_DATABASE_URL": connection_string,
            "CRASH_TEST_EXECUTION_ID": execution_id,
            "CRASH_TEST_MARKER": marker,
        }
        try:
            first = subprocess.Popen(
                [sys.executable, "-m", worker_module],
                env={
                    **base_environment,
                    "CRASH_TEST_MODE": "block",
                    "CRASH_TEST_OWNER": "crash-owner-a",
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            for _ in range(200):
                if Path(marker).exists():
                    break
                if first.poll() is not None:
                    stderr = first.stderr.read()
                    raise AssertionError(
                        "first crash worker exited early: "
                        + stderr.decode(errors="replace")[-1000:]
                    )
                await asyncio.sleep(0.05)
            assert Path(marker).exists(), "first worker never entered model node"
            assert await checkpointer.aget_tuple(
                {
                    "configurable": {
                        "thread_id": execution_id,
                        "checkpoint_ns": "",
                    }
                }
            ) is not None

            first.kill()
            await asyncio.to_thread(first.wait)
            first = None
            await asyncio.sleep(3.2)

            try:
                second = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", worker_module],
                    env={
                        **base_environment,
                        "CRASH_TEST_MODE": "complete",
                        "CRASH_TEST_OWNER": "crash-owner-b",
                    },
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=20,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise
            assert second.returncode == 0, second.stderr.decode(
                errors="replace"
            )[-1000:]

            events = await store.events_after(execution_id, 0)
            assert [event.sequence for event in events] == list(
                range(1, len(events) + 1)
            )
            event_types = [event.type for event in events]
            assert event_types.count("run.started") == 1
            assert event_types.count("run.resumed") == 1
            assert event_types.count("answer.delta") == 1
            assert event_types[-1] == "run.completed"
            assert (
                await store.get_execution(execution_id)
            ).status == RunStatus.COMPLETED
        finally:
            if first is not None and first.poll() is None:
                first.kill()
                await asyncio.to_thread(first.wait)
            await checkpointer.adelete_thread(execution_id)
            async with store._pool.connection() as connection:
                await connection.execute(
                    """
                    DELETE FROM agent_runtime.runtime_executions
                    WHERE execution_id = %s
                    """,
                    (execution_id,),
                )
            await store.close()
