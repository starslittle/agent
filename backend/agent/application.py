from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from typing import Any

from agent.capabilities import (
    CapabilityExecutor,
    RegistryCapabilityExecutor,
    TARGET_CAPABILITY_SPECS,
)
from agent.context import (
    RUN_CONTEXT_KEY,
    RUNTIME_LEASE_KEY,
    RunContext,
    RuntimeLease,
)
from agent.events import emit_model_event
from agent.graph import build_root_graph
from agent.models import (
    ModelGateway,
    ObservedModelGateway,
    ModelCatalog,
    get_model_catalog,
    get_model_gateway,
)
from agent.prompts import prompt_sha256
from agent.root import RootSkillResolver, SkillRouteResolution, context_requirements_for
from agent.specs import (
    PROMPT_BUNDLES,
    AgentCatalog,
    get_agent_catalog,
)
from agent.state import create_root_state
from agent.skills import (
    SkillRegistry,
    SkillSelection,
    get_skill_registry,
    resolve_compatible_selection,
)


@dataclass(frozen=True)
class RunCommand:
    execution_id: str
    query: str
    messages: list[dict[str, str]]
    requested_workflow: str
    model_id: str = "auto"
    selection: SkillSelection | None = None
    resolution: SkillRouteResolution | None = None
    context_package_id: str | None = None
    context_package: dict[str, Any] | None = None
    shadow: bool = False
    deadline_ms: int = 120_000
    cancel_event: asyncio.Event | None = None
    lease: RuntimeLease | None = None
    resume: bool = False


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    data: dict[str, Any]


class LangGraphAgentApplication:
    """The only target entry point into the compiled Python agent graph."""

    def __init__(
        self,
        *,
        gateway: ModelGateway | None = None,
        capability_executor: CapabilityExecutor | None = None,
        catalog: AgentCatalog | None = None,
        skill_registry: SkillRegistry | None = None,
        model_catalog: ModelCatalog | None = None,
        skill_resolver: RootSkillResolver | None = None,
        checkpointer=None,
        lease_guard=None,
        artifact_stager=None,
    ) -> None:
        raw_gateway = gateway or get_model_gateway()
        self._gateway = ObservedModelGateway(
            raw_gateway,
            emit_model_event,
        )
        self._capabilities = capability_executor or RegistryCapabilityExecutor()
        self._catalog = catalog or get_agent_catalog()
        self._skill_registry = skill_registry or get_skill_registry()
        self._model_catalog = model_catalog or get_model_catalog()
        self._skill_resolver = skill_resolver or RootSkillResolver(
            gateway=raw_gateway,
            skill_registry=self._skill_registry,
            model_catalog=self._model_catalog,
        )
        self._checkpointer = checkpointer
        self._lease_guard = lease_guard
        self._artifact_stager = artifact_stager
        self._graph = build_root_graph(
            self._gateway,
            self._capabilities,
            self._catalog,
            checkpointer,
            skill_registry=self._skill_registry,
        )

    async def has_checkpoint(self, execution_id: str) -> bool:
        if self._checkpointer is None:
            return False
        checkpoint = await self._checkpointer.aget_tuple(
            {
                "configurable": {
                    "thread_id": execution_id,
                    "checkpoint_ns": "",
                }
            }
        )
        return checkpoint is not None

    def describe_provenance(
        self,
        requested_workflow: str,
        *,
        model_id: str = "auto",
        selection: SkillSelection | None = None,
        resolution: SkillRouteResolution | None = None,
        context_package_id: str | None = None,
    ) -> dict[str, Any]:
        if resolution is not None:
            requested_workflow = resolution.workflow
            selection = resolution.as_selection()
        spec = self._catalog.resolve(requested_workflow)
        profile = self._gateway.profile(spec.model_profile)
        resolved_model = self._model_catalog.resolve(model_id)
        selected_skill = None
        if selection is not None and selection.primary_skill is not None:
            selected_skill = self._skill_registry.resolve(selection.primary_skill)
            if selected_skill.workflow != spec.workflow:
                raise ValueError("Skill workflow does not match compatibility spec")
        prompt_versions = {
            stage: {
                "path": path,
                "sha256": prompt_sha256(path),
            }
            for stage, path in sorted(PROMPT_BUNDLES[spec.prompt_bundle].items())
        }
        prompt_bundle_hash = hashlib.sha256(
            json.dumps(
                prompt_versions,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        allowed_capabilities = (
            selected_skill.allowed_capabilities
            if selected_skill is not None
            else spec.allowed_capabilities
        )
        capabilities = [
            {
                "name": capability.name,
                "version": capability.version,
                "effect": capability.effect,
                "idempotent": capability.idempotent,
            }
            for capability in (
                TARGET_CAPABILITY_SPECS[name] for name in sorted(allowed_capabilities)
            )
        ]
        skill_snapshot = None
        if selected_skill is not None:
            skill_snapshot = {
                **selected_skill.model_dump(mode="json"),
                "allowed_capabilities": sorted(selected_skill.allowed_capabilities),
                "fingerprint": self._skill_registry.fingerprint(),
            }
        model_snapshot = {
            **resolved_model.model_dump(mode="json"),
            "execution_profile": spec.model_profile,
            "execution_provider": profile.provider,
            "execution_model": profile.model,
            "execution_capabilities": profile.capabilities.model_dump(mode="json"),
        }
        return {
            "workflow_name": spec.workflow,
            "workflow_version": spec.workflow.rsplit("_v", 1)[-1],
            "agent_name": spec.name,
            "agent_spec_hash": self._catalog.fingerprint(),
            "model_profile": spec.model_profile,
            "model_provider": profile.provider,
            "model_name": profile.model,
            "prompt_bundle": spec.prompt_bundle,
            "prompt_bundle_hash": prompt_bundle_hash,
            "prompt_versions": prompt_versions,
            "capabilities": capabilities,
            "model_id": resolved_model.model_id,
            "model_catalog_fingerprint": self._model_catalog.fingerprint(),
            "model_snapshot": model_snapshot,
            "requested_skill": (
                selection.requested_skill if selection is not None else None
            ),
            "resolved_skills": (
                selection.resolved_skills if selection is not None else []
            ),
            "primary_skill": (
                selection.primary_skill if selection is not None else None
            ),
            "selection_source": (
                selection.selection_source if selection is not None else "direct"
            ),
            "skill_snapshot": skill_snapshot,
            "context_package_id": context_package_id,
            "route_confidence": (
                resolution.confidence if resolution is not None else 1.0
            ),
            "route_requires_confirmation": (
                resolution.requires_confirmation if resolution is not None else False
            ),
            "route_reason_code": (
                resolution.reason_code if resolution is not None else "pre_resolved"
            ),
            "suggested_skill": (
                resolution.suggested_skill if resolution is not None else None
            ),
            "route_prompt": {
                "path": "agent/prompts/skill_route_v1.txt",
                "sha256": prompt_sha256("agent/prompts/skill_route_v1.txt"),
            },
        }

    async def resolve_command(self, command: RunCommand) -> RunCommand:
        if command.resolution is not None:
            return command
        selection = command.selection or resolve_compatible_selection(
            requested_skill=None,
            agent_name=command.requested_workflow,
            registry=self._skill_registry,
        )
        resolution = await self._skill_resolver.resolve(
            query=command.query,
            model_id=command.model_id,
            selection=selection,
        )
        return replace(
            command,
            requested_workflow=resolution.workflow,
            selection=resolution.as_selection(),
            resolution=resolution,
        )

    async def resolve_route(
        self, command: RunCommand
    ) -> tuple[RunCommand, dict[str, Any], dict[str, Any]]:
        resolved = await self.resolve_command(command)
        provenance = self.describe_provenance(
            resolved.requested_workflow,
            model_id=resolved.model_id,
            selection=resolved.selection,
            resolution=resolved.resolution,
        )
        requirements = context_requirements_for(resolved.resolution)
        return resolved, provenance, requirements.model_dump(mode="json")

    async def stream(
        self,
        command: RunCommand,
    ) -> AsyncIterator[RuntimeEvent]:
        command = await self.resolve_command(command)
        messages = list(command.messages)
        if command.context_package is not None and command.context_package.get("items"):
            lines = ["以下是用户已确认、仅供本次请求使用的个人上下文："]
            for item in command.context_package["items"]:
                lines.append(f"- [{item['type']}/{item['domain']}] {item['content']}")
            messages.append({"role": "user", "content": "\n".join(lines)})
        state = (
            None
            if command.resume
            else create_root_state(
                query=command.query,
                messages=messages,
                context_package=command.context_package,
                requested_workflow=command.requested_workflow,
                resolution=command.resolution,
                execution_id=command.execution_id,
                shadow=command.shadow,
            )
        )
        spec = self._catalog.resolve(command.resolution.workflow)
        skill = (
            self._skill_registry.resolve(command.resolution.primary_skill)
            if command.resolution.primary_skill is not None
            else None
        )
        policy_deadline = (
            skill.budgets.deadline_seconds
            if skill is not None
            else spec.budgets.deadline_seconds
        )
        deadline_seconds = min(
            command.deadline_ms / 1000,
            policy_deadline,
        )
        cancel_event = command.cancel_event or asyncio.Event()
        context = RunContext(
            execution_id=command.execution_id,
            shadow=command.shadow,
            cancel_event=cancel_event,
            deadline_at=time.monotonic() + deadline_seconds,
            lease=command.lease,
            lease_validator=(
                self._lease_guard.assert_lease
                if self._lease_guard is not None
                else None
            ),
            artifact_stager=(
                self._artifact_stager.stage_artifact
                if self._artifact_stager is not None
                else None
            ),
        )
        context.raise_if_stopped()
        async with asyncio.timeout(deadline_seconds):
            async for item in self._graph.astream(
                state,
                config={
                    "configurable": {
                        "thread_id": command.execution_id,
                        "checkpoint_ns": "",
                        RUN_CONTEXT_KEY: context,
                        **(
                            {RUNTIME_LEASE_KEY: command.lease}
                            if command.lease is not None
                            else {}
                        ),
                    }
                },
                stream_mode=["custom", "updates"],
                subgraphs=True,
            ):
                if not isinstance(item, tuple):
                    continue
                if len(item) == 3:
                    _, mode, value = item
                elif len(item) == 2:
                    mode, value = item
                else:
                    continue
                if mode != "custom":
                    continue
                if not isinstance(value, dict) or "type" not in value:
                    continue
                yield RuntimeEvent(
                    type=str(value["type"]),
                    data=dict(value.get("data") or {}),
                )
            # LangGraph may finish its iterator after a cancelled node task.
            # Re-check the authoritative run signal before reporting a normal
            # stream completion to the protocol adapter.
            context.raise_if_stopped()
