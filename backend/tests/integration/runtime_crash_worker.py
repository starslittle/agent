from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agent.application import LangGraphAgentApplication
from agent.models import (
    ModelCapabilities,
    ModelProfile,
    ModelStreamEvent,
    ModelStreamEventType,
)
from app.runtime.langgraph_v1 import LangGraphV1Runtime
from app.runtime.models import AgentRunRequest
from app.runtime.postgres_store import PostgresRuntimeStore
from app.runtime.registry import ExecutionRegistry


class CrashTestGateway:
    def __init__(self, mode: str, marker: str) -> None:
        self._mode = mode
        self._marker = marker
        self._profile = ModelProfile(
            name="default_chat",
            provider="fake",
            model="fake-crash-test",
            max_retries=0,
            capabilities=ModelCapabilities(streaming=True),
        )

    def profile(self, profile_name):
        return self._profile.model_copy(update={"name": profile_name})

    async def stream(self, profile_name, request):
        if self._mode == "block":
            Path(self._marker).touch()
            await asyncio.sleep(3600)
            return
        yield ModelStreamEvent(
            type=ModelStreamEventType.DELTA,
            text="resumed-once",
            model="fake-crash-test",
        )
        yield ModelStreamEvent(
            type=ModelStreamEventType.COMPLETED,
            model="fake-crash-test",
            finish_reason="stop",
        )

    async def structured(self, profile_name, request, output_type):
        raise AssertionError("chat crash test must not call structured output")


class NoCapabilities:
    async def execute(self, *args, **kwargs):
        raise AssertionError("chat crash test must not call capabilities")


def request_for(execution_id: str) -> AgentRunRequest:
    return AgentRunRequest(
        execution_id=execution_id,
        run_id=f"run-{execution_id}",
        request_id=f"request-{execution_id}",
        idempotency_key=f"idem-{execution_id}",
        conversation_id="crash-test",
        agent_name="default_llm_agent",
        query="crash and resume",
        deadline_ms=30_000,
    )


async def main() -> None:
    connection_string = os.environ["TEST_DATABASE_URL"]
    execution_id = os.environ["CRASH_TEST_EXECUTION_ID"]
    mode = os.environ["CRASH_TEST_MODE"]
    marker = os.environ["CRASH_TEST_MARKER"]
    owner_id = os.environ["CRASH_TEST_OWNER"]

    store = await PostgresRuntimeStore.open(connection_string)
    try:
        checkpointer = await store.build_checkpointer(setup=False)
        application = LangGraphAgentApplication(
            gateway=CrashTestGateway(mode, marker),
            capability_executor=NoCapabilities(),
            checkpointer=checkpointer,
            lease_guard=store,
            artifact_stager=store,
        )
        registry = ExecutionRegistry(
            LangGraphV1Runtime(application=application),
            service_version="crash-test",
            store=store,
            owner_id=owner_id,
            lease_seconds=3,
            event_poll_seconds=0.05,
        )
        execution = await registry.start(request_for(execution_id))
        async for _ in registry.events(execution):
            pass
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(main())
