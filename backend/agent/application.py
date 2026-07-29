from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
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
    get_model_gateway,
)
from agent.prompts import prompt_sha256
from agent.specs import (
    PROMPT_BUNDLES,
    AgentCatalog,
    get_agent_catalog,
)
from agent.state import create_root_state


@dataclass(frozen=True)
class RunCommand:
    execution_id: str
    query: str
    messages: list[dict[str, str]]
    requested_workflow: str
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
        checkpointer=None,
        lease_guard=None,
        artifact_stager=None,
    ) -> None:
        self._gateway = ObservedModelGateway(
            gateway or get_model_gateway(),
            emit_model_event,
        )
        self._capabilities = (
            capability_executor or RegistryCapabilityExecutor()
        )
        self._catalog = catalog or get_agent_catalog()
        self._checkpointer = checkpointer
        self._lease_guard = lease_guard
        self._artifact_stager = artifact_stager
        self._graph = build_root_graph(
            self._gateway,
            self._capabilities,
            self._catalog,
            checkpointer,
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
    ) -> dict[str, Any]:
        spec = self._catalog.resolve(requested_workflow)
        profile = self._gateway.profile(spec.model_profile)
        prompt_versions = {
            stage: {
                "path": path,
                "sha256": prompt_sha256(path),
            }
            for stage, path in sorted(
                PROMPT_BUNDLES[spec.prompt_bundle].items()
            )
        }
        prompt_bundle_hash = hashlib.sha256(
            json.dumps(
                prompt_versions,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        capabilities = [
            {
                "name": capability.name,
                "version": capability.version,
                "effect": capability.effect,
                "idempotent": capability.idempotent,
            }
            for capability in (
                TARGET_CAPABILITY_SPECS[name]
                for name in sorted(spec.allowed_capabilities)
            )
        ]
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
        }

    async def stream(
        self,
        command: RunCommand,
    ) -> AsyncIterator[RuntimeEvent]:
        state = (
            None
            if command.resume
            else create_root_state(
                query=command.query,
                messages=command.messages,
                requested_workflow=command.requested_workflow,
                execution_id=command.execution_id,
                shadow=command.shadow,
            )
        )
        spec = self._catalog.resolve(command.requested_workflow)
        deadline_seconds = min(
            command.deadline_ms / 1000,
            spec.budgets.deadline_seconds,
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
