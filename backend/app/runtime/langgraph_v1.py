from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent.application import LangGraphAgentApplication, RunCommand
from agent.capabilities import RegistryCapabilityExecutor
from agent.models import get_model_gateway
from agent.documents import (
    DOCUMENT_EXTRACTION_AGENT,
    DOCUMENT_EXTRACTION_PURPOSE,
    DocumentExtractor,
    parse_extraction_envelope,
)
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
        document_extractor: DocumentExtractor | None = None,
    ) -> None:
        gateway = get_model_gateway()
        self._application = application or LangGraphAgentApplication(
            gateway=gateway,
            capability_executor=RegistryCapabilityExecutor(),
            checkpointer=checkpointer,
            lease_guard=lease_guard,
            artifact_stager=artifact_stager,
        )
        self._document_extractor = document_extractor or DocumentExtractor(gateway)
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
        envelope = self._document_envelope(request)
        if envelope is not None:
            yield "document.extraction.started", {
                "run_purpose": DOCUMENT_EXTRACTION_PURPOSE,
                "document_id": envelope.document_id,
                "document_revision_id": envelope.document_revision_id,
                "extraction_version": envelope.extraction_version,
                "stage": "document.extract",
            }
            yield "prompt.rendered", {
                "stage": "document.extract",
                "path": "agent/prompts/document_extract_v1.txt",
                "prompt_hash": self._document_extractor.prompt_hash,
                "rendered_characters": len(envelope.markdown),
            }
            if cancel_event.is_set():
                raise asyncio.CancelledError
            data = await self._document_extractor.event_data(envelope)
            if cancel_event.is_set():
                raise asyncio.CancelledError
            yield "document.extraction.completed", data
            yield "answer.delta", {
                "text": f"已生成 {data['candidate_count']} 条待确认候选。"
            }
            return
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
        if self._document_envelope(request) is not None:
            provenance = self._document_extractor.provenance()
            provenance["context_package_id"] = request.context_package_id
            return provenance
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
        envelope = parse_extraction_envelope(request.query)
        if request.agent_name == DOCUMENT_EXTRACTION_AGENT and envelope is not None:
            provenance = self._document_extractor.provenance()
            return {
                "resolution": {
                    "model_id": "auto",
                    "requested_skill": None,
                    "resolved_skills": [],
                    "primary_skill": None,
                    "suggested_skill": None,
                    "confidence": 1.0,
                    "selection_source": "direct",
                    "requires_confirmation": False,
                    "reason_code": DOCUMENT_EXTRACTION_PURPOSE,
                    "agent_name": DOCUMENT_EXTRACTION_AGENT,
                    "workflow": "document_extraction_v1",
                    "skill_version": None,
                    "skill_snapshot": None,
                    "model_snapshot": provenance["model_snapshot"],
                    "context_package_id": None,
                },
                "context_requirements": {
                    "execution_mode": "direct",
                    "primary_skill": None,
                    "purpose": DOCUMENT_EXTRACTION_PURPOSE,
                    "needs_personal_context": False,
                    "allowed_types": [],
                    "allowed_domains": [],
                    "item_budget": 0,
                    "character_budget": 0,
                },
                "route_usage": {"model_calls": 0},
            }
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
    def _document_envelope(request: AgentRunRequest):
        if request.route_reason_code != DOCUMENT_EXTRACTION_PURPOSE:
            return None
        return parse_extraction_envelope(request.query)

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
