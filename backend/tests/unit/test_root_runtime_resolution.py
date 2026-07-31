from __future__ import annotations

import pytest

from agent.application import LangGraphAgentApplication
from agent.models.factory import default_model_profiles
from agent.root import SkillRouteProposal
from app.runtime.langgraph_v1 import LangGraphV1Runtime
from app.runtime.models import AgentRunRequest
from app.runtime.registry import ExecutionRegistry
from app.runtime.store import InMemoryRuntimeStore


class FrozenRouteGateway:
    def __init__(self, proposal: SkillRouteProposal):
        self.proposal = proposal
        self.calls = 0

    def profile(self, profile_name):
        return {
            profile.name: profile for profile in default_model_profiles()
        }[profile_name]

    async def structured(self, profile_name, request, output_type):
        self.calls += 1
        if output_type is not SkillRouteProposal:
            raise AssertionError(output_type)
        return self.proposal


def _request(execution_id: str, query: str) -> AgentRunRequest:
    return AgentRunRequest(
        execution_id=execution_id,
        run_id=f"run-{execution_id}",
        request_id=f"request-{execution_id}",
        idempotency_key=f"idempotency-{execution_id}",
        conversation_id=f"conversation-{execution_id}",
        query=query,
    )


@pytest.mark.asyncio
async def test_runtime_provenance_contains_the_frozen_automatic_resolution():
    gateway = FrozenRouteGateway(
        SkillRouteProposal(
            route="research",
            confidence=0.91,
            reason_code="needs_current_sources",
        )
    )
    runtime = LangGraphV1Runtime(
        application=LangGraphAgentApplication(gateway=gateway)
    )
    provenance = await runtime.describe_provenance(
        _request("exec-auto-route", "请检索最新资料并列出来源")
    )

    assert provenance["resolved_skills"] == ["research"]
    assert provenance["primary_skill"] == "research"
    assert provenance["selection_source"] == "automatic"
    assert provenance["route_confidence"] == 0.91
    assert provenance["route_reason_code"] == "needs_current_sources"
    assert provenance["workflow_name"] == "research_v1"


@pytest.mark.asyncio
async def test_registry_freezes_confirmation_before_execution_and_event_write():
    gateway = FrozenRouteGateway(
        SkillRouteProposal(
            route="fortune",
            confidence=0.97,
            reason_code="fortune_request",
        )
    )
    runtime = LangGraphV1Runtime(
        application=LangGraphAgentApplication(gateway=gateway)
    )
    registry = ExecutionRegistry(
        runtime,
        service_version="test",
        store=InMemoryRuntimeStore(),
    )
    execution = await registry.start(
        _request("exec-frozen-confirmation", "请看看我的命盘")
    )
    events = [event async for event in registry.events(execution)]

    resolved = next(event for event in events if event.type == "run.resolved")
    assert resolved.data["resolved_skills"] == []
    assert resolved.data["suggested_skill"] == "fortune"
    assert resolved.data["requires_confirmation"] is True
    assert any(event.type == "confirmation.required" for event in events)
    assert all(not event.type.startswith("tool.") for event in events)
    assert gateway.calls == 1
