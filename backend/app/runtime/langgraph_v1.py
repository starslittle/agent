from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent.application import LangGraphAgentApplication, RunCommand
from agent.capabilities import RegistryCapabilityExecutor
from agent.models import get_model_gateway
from agent.root import SkillRouteResolution
from agent.skills import (
    SkillSelection,
    get_skill_registry,
    resolve_compatible_selection,
)

from .models import AgentRouteRequest, AgentRunRequest
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
        selection = self._selection(request)
        resolution = self._resolution(request, selection)
        command = RunCommand(
            execution_id=request.execution_id,
            query=request.query,
            messages=[item.model_dump() for item in request.messages],
            requested_workflow=request.mode or selection.agent_name,
            model_id=request.model_id,
            selection=selection,
            resolution=resolution,
            context_package_id=request.context_package_id,
            context_package=(
                request.context_package.model_dump(mode="json")
                if request.context_package is not None
                else None
            ),
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
        selection = self._selection(request)
        resolution = self._resolution(request, selection)
        command = await self._application.resolve_command(
            RunCommand(
                execution_id=request.execution_id,
                query=request.query,
                messages=[item.model_dump() for item in request.messages],
                requested_workflow=request.mode or selection.agent_name,
                model_id=request.model_id,
                selection=selection,
                resolution=resolution,
                context_package_id=request.context_package_id,
                shadow=request.shadow,
                deadline_ms=request.deadline_ms,
            )
        )
        return self._application.describe_provenance(
            command.requested_workflow,
            model_id=request.model_id,
            selection=command.selection,
            resolution=command.resolution,
            context_package_id=request.context_package_id,
        )

    async def resolve_route(self, request: AgentRouteRequest) -> dict:
        selection = resolve_compatible_selection(
            requested_skill=request.requested_skill,
            agent_name=request.agent_name,
        )
        command, provenance, requirements = await self._application.resolve_route(
            RunCommand(
                execution_id=request.execution_id,
                query=request.query,
                messages=[item.model_dump() for item in request.messages],
                requested_workflow=selection.agent_name,
                model_id=request.model_id,
                selection=selection,
            )
        )
        resolution = command.resolution.model_dump(mode="json")
        resolution.update(
            {
                "model_id": provenance["model_id"],
                "skill_snapshot": provenance["skill_snapshot"],
                "model_snapshot": provenance["model_snapshot"],
                "context_package_id": None,
            }
        )
        route_model_used = (
            command.resolution.selection_source in {"automatic", "direct", "fallback"}
            and request.requested_skill is None
        )
        return {
            "resolution": resolution,
            "context_requirements": requirements,
            "route_usage": {"model_calls": 1 if route_model_used else 0},
        }

    @staticmethod
    def _selection(request: AgentRunRequest) -> SkillSelection:
        if request.selection_source is None:
            return resolve_compatible_selection(
                requested_skill=request.requested_skill,
                agent_name=request.agent_name,
            )
        registry = get_skill_registry()
        if request.primary_skill is None:
            return SkillSelection(
                requested_skill=request.requested_skill,
                resolved_skills=[],
                primary_skill=None,
                selection_source=request.selection_source,
                agent_name="default_llm_agent",
                workflow="chat_v1",
            )
        skill = registry.resolve(request.primary_skill)
        agent_name = f"{skill.id}_agent"
        return SkillSelection(
            requested_skill=request.requested_skill,
            resolved_skills=request.resolved_skills,
            primary_skill=skill.id,
            selection_source=request.selection_source,
            agent_name=agent_name,
            workflow=skill.workflow,
            skill_version=skill.version,
        )

    @staticmethod
    def _resolution(
        request: AgentRunRequest,
        selection: SkillSelection,
    ) -> SkillRouteResolution | None:
        if request.route_reason_code is None:
            return None
        return SkillRouteResolution(
            requested_skill=request.requested_skill,
            resolved_skills=request.resolved_skills,
            primary_skill=request.primary_skill,
            suggested_skill=request.suggested_skill,
            confidence=request.route_confidence or 0,
            selection_source=request.selection_source or "direct",
            requires_confirmation=request.route_requires_confirmation,
            reason_code=request.route_reason_code,
            agent_name=selection.agent_name,
            workflow=selection.workflow,
            skill_version=selection.skill_version,
        )

    async def cancel(self, execution_id: str) -> None:
        from agent.tools.registry import get_tool_registry

        await get_tool_registry().cancel_execution(execution_id)
        task = self._active_tasks.get(execution_id)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
