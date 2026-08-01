from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from agent.models import UnknownModelIDError
from agent.skills import (
    ConflictingSkillRequestError,
    UnknownRequestedSkillError,
    resolve_compatible_selection,
)
from app.runtime.langgraph_v1 import LangGraphV1Runtime
from app.runtime.models import AgentRunRequest


def _request(**changes) -> AgentRunRequest:
    values = {
        "execution_id": "exec-skill-contract",
        "run_id": "run-skill-contract",
        "request_id": "request-skill-contract",
        "idempotency_key": "idempotency-skill-contract",
        "conversation_id": "conversation-skill-contract",
        "query": "hello",
    }
    values.update(changes)
    return AgentRunRequest(**values)


def test_direct_and_explicit_skill_selection_are_stable():
    direct = resolve_compatible_selection(
        requested_skill=None,
        agent_name="default_llm_agent",
    )
    research = resolve_compatible_selection(
        requested_skill="research",
        agent_name="default_llm_agent",
    )

    assert direct.model_dump() == {
        "requested_skill": None,
        "resolved_skills": [],
        "primary_skill": None,
        "selection_source": "direct",
        "agent_name": "default_llm_agent",
        "workflow": "chat_v1",
        "skill_version": None,
    }
    assert research.requested_skill == "research"
    assert research.resolved_skills == ["research"]
    assert research.agent_name == "research_agent"
    assert research.selection_source == "user"


def test_legacy_agent_mapping_is_centralized_and_conflicts_fail():
    fortune = resolve_compatible_selection(
        requested_skill=None,
        agent_name="fortune_agent",
    )
    assert fortune.requested_skill == "fortune"
    assert fortune.selection_source == "compatibility"
    legacy_wire = resolve_compatible_selection(
        requested_skill="research",
        agent_name="research_agent",
    )
    assert legacy_wire.selection_source == "compatibility"
    explicit_wire = resolve_compatible_selection(
        requested_skill="research",
        agent_name="research",
    )
    assert explicit_wire.selection_source == "user"

    with pytest.raises(UnknownRequestedSkillError):
        resolve_compatible_selection(
            requested_skill="decision",
            agent_name="default_llm_agent",
        )
    with pytest.raises(ConflictingSkillRequestError):
        resolve_compatible_selection(
            requested_skill="research",
            agent_name="fortune_agent",
        )


def test_request_rejects_invalid_skill_projection_and_bounds():
    with pytest.raises(ValidationError):
        _request(resolved_skills=["research"], primary_skill=None)
    with pytest.raises(ValidationError):
        _request(resolved_skills=["research", "fortune"])
    with pytest.raises(ValidationError):
        _request(requested_skill="")


@pytest.mark.asyncio
async def test_provenance_seals_model_and_skill_snapshots():
    runtime = LangGraphV1Runtime()
    provenance = await runtime.describe_provenance(
        _request(requested_skill="research")
    )

    assert provenance["model_id"] == "auto"
    assert provenance["requested_skill"] == "research"
    assert provenance["resolved_skills"] == ["research"]
    assert provenance["primary_skill"] == "research"
    assert provenance["selection_source"] == "user"
    assert provenance["skill_snapshot"]["version"] == 2
    assert provenance["model_snapshot"]["fingerprint"]
    assert provenance["workflow_name"] == "research_v1"


@pytest.mark.asyncio
async def test_unknown_model_fails_before_execution():
    runtime = LangGraphV1Runtime()
    with pytest.raises(UnknownModelIDError):
        await runtime.describe_provenance(_request(model_id="missing"))


@pytest.mark.asyncio
async def test_runtime_emits_resolution_before_application_events():
    class FakeApplication:
        async def stream(self, command):
            assert command.selection.primary_skill == "research"
            yield type("Event", (), {"type": "answer.delta", "data": {"text": "ok"}})()

        def describe_provenance(self, *args, **kwargs):
            return {}

    runtime = LangGraphV1Runtime(application=FakeApplication())
    events = [
        item
        async for item in runtime.stream(
            _request(requested_skill="research"),
            asyncio.Event(),
        )
    ]
    assert events == [("answer.delta", {"text": "ok"})]


@pytest.mark.asyncio
async def test_runtime_preserves_frozen_direct_capability():
    class FakeApplication:
        async def stream(self, command):
            assert command.resolution.direct_capability == "get_weather"
            assert command.resolution.direct_capability_arguments == {
                "location": "杭州"
            }
            yield type("Event", (), {"type": "answer.delta", "data": {"text": "ok"}})()

    runtime = LangGraphV1Runtime(application=FakeApplication())
    request = _request(
        selection_source="direct",
        route_reason_code="needs_current_sources",
        direct_capability="get_weather",
        direct_capability_arguments={"location": "杭州"},
    )

    events = [item async for item in runtime.stream(request, asyncio.Event())]

    assert events == [("answer.delta", {"text": "ok"})]
