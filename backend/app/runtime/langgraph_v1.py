from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent.application import LangGraphAgentApplication, RunCommand
from agent.capabilities import RegistryCapabilityExecutor
from agent.models import get_model_gateway

from .models import AgentRunRequest
from .store import LeaseToken


class LangGraphV1Runtime:
    """V1 protocol adapter for the target compiled Agent Application."""

    graph_version = "qidian-root-v1"
    supports_lease_context = True
    supports_checkpoint_recovery = True

    def __init__(
        self,
        application: LangGraphAgentApplication | None = None,
        *,
        checkpointer=None,
        lease_guard=None,
        artifact_stager=None,
    ) -> None:
        self._application = application or LangGraphAgentApplication(
            gateway=get_model_gateway(),
            capability_executor=RegistryCapabilityExecutor(),
            checkpointer=checkpointer,
            lease_guard=lease_guard,
            artifact_stager=artifact_stager,
        )
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def stream(
        self,
        request: AgentRunRequest,
        cancel_event: asyncio.Event,
        *,
        lease: LeaseToken | None = None,
        resume: bool = False,
    ) -> AsyncIterator[tuple[str, dict]]:
        task = asyncio.current_task()
        if task is not None:
            self._active_tasks[request.execution_id] = task
        command = RunCommand(
            execution_id=request.execution_id,
            query=request.query,
            messages=[item.model_dump() for item in request.messages],
            requested_workflow=request.mode or request.agent_name,
            shadow=request.shadow,
            deadline_ms=request.deadline_ms,
            cancel_event=cancel_event,
            lease=lease,
            resume=resume,
        )
        try:
            async for event in self._application.stream(command):
                if cancel_event.is_set():
                    raise asyncio.CancelledError
                yield event.type, event.data
        finally:
            self._active_tasks.pop(request.execution_id, None)

    async def can_resume(self, execution_id: str) -> bool:
        return await self._application.has_checkpoint(execution_id)

    async def describe_provenance(
        self,
        request: AgentRunRequest,
    ) -> dict:
        return self._application.describe_provenance(
            request.mode or request.agent_name
        )

    async def cancel(self, execution_id: str) -> None:
        from agent.tools.registry import get_tool_registry

        await get_tool_registry().cancel_execution(execution_id)
        task = self._active_tasks.get(execution_id)
        if (
            task is not None
            and not task.done()
            and task is not asyncio.current_task()
        ):
            task.cancel()
