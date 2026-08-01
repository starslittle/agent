from __future__ import annotations

import pytest

from agent.application import LangGraphAgentApplication, RunCommand
from agent.models import get_model_catalog
from agent.models.factory import default_model_profiles
from agent.root import (
    RootSkillResolver,
    SkillPolicyError,
    SkillRouteProposal,
)
from agent.skills import get_skill_registry, resolve_compatible_selection


class RouteGateway:
    def __init__(self, proposal: SkillRouteProposal | Exception):
        self.proposal = proposal
        self.calls = 0

    def profile(self, profile_name):
        return {
            profile.name: profile for profile in default_model_profiles()
        }[profile_name]

    async def structured(self, profile_name, request, output_type):
        self.calls += 1
        assert profile_name == "default_chat"
        assert output_type is SkillRouteProposal
        assert request.tools == []
        if isinstance(self.proposal, Exception):
            raise self.proposal
        return self.proposal


def _selection(skill: str | None = None, agent_name: str = "default_llm_agent"):
    return resolve_compatible_selection(
        requested_skill=skill,
        agent_name=agent_name,
    )


def _resolver(gateway, *, allowed_skill_ids: set[str] | None = None):
    return RootSkillResolver(
        gateway=gateway,
        skill_registry=get_skill_registry(),
        model_catalog=get_model_catalog(),
        allowed_skill_ids=allowed_skill_ids,
    )


@pytest.mark.asyncio
async def test_explicit_skill_skips_route_model_but_still_checks_policy():
    gateway = RouteGateway(RuntimeError("must not be called"))
    resolution = await _resolver(gateway).resolve(
        query="请检索并给出来源",
        model_id="auto",
        selection=_selection("research"),
    )

    assert gateway.calls == 0
    assert resolution.resolved_skills == ["research"]
    assert resolution.selection_source == "user"
    assert resolution.requires_confirmation is False

    with pytest.raises(SkillPolicyError) as denied:
        await _resolver(gateway, allowed_skill_ids=set()).resolve(
            query="请检索并给出来源",
            model_id="auto",
            selection=_selection("research"),
        )
    assert denied.value.code == "skill_not_allowed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confidence", "resolved", "confirmation", "source"),
    [
        (0.549, [], False, "fallback"),
        (0.55, [], True, "automatic"),
        (0.849, [], True, "automatic"),
        (0.85, ["research"], False, "automatic"),
    ],
)
async def test_research_confidence_boundaries_are_stable(
    confidence,
    resolved,
    confirmation,
    source,
):
    gateway = RouteGateway(
        SkillRouteProposal(
            route="research",
            confidence=confidence,
            reason_code="needs_current_sources",
        )
    )
    resolution = await _resolver(gateway).resolve(
        query="请调查最近的公开资料",
        model_id="auto",
        selection=_selection(),
    )

    assert resolution.resolved_skills == resolved
    assert resolution.requires_confirmation is confirmation
    assert resolution.selection_source == source


@pytest.mark.asyncio
async def test_automatic_fortune_always_requires_confirmation():
    gateway = RouteGateway(
        SkillRouteProposal(
            route="fortune",
            confidence=0.99,
            reason_code="fortune_request",
        )
    )
    resolution = await _resolver(gateway).resolve(
        query="请根据出生信息看一下命盘",
        model_id="auto",
        selection=_selection(),
    )

    assert resolution.resolved_skills == []
    assert resolution.suggested_skill == "fortune"
    assert resolution.requires_confirmation is True


@pytest.mark.asyncio
async def test_direct_and_route_failure_never_select_a_tool_skill():
    direct = await _resolver(
        RouteGateway(
            SkillRouteProposal(
                route="direct",
                confidence=0.96,
                reason_code="general_conversation",
            )
        )
    ).resolve(query="你好", model_id="auto", selection=_selection())
    fallback = await _resolver(RouteGateway(RuntimeError("offline"))).resolve(
        query="你好",
        model_id="auto",
        selection=_selection(),
    )

    assert direct.resolved_skills == []
    assert direct.selection_source == "direct"
    assert fallback.resolved_skills == []
    assert fallback.selection_source == "fallback"
    assert fallback.reason_code == "route_model_failed"


@pytest.mark.asyncio
async def test_direct_route_can_select_one_schema_validated_current_info_tool():
    resolution = await _resolver(
        RouteGateway(
            SkillRouteProposal(
                route="direct",
                confidence=0.98,
                reason_code="needs_current_sources",
                direct_capability="get_weather",
                direct_capability_arguments={"location": "杭州"},
            )
        )
    ).resolve(query="杭州今天天气", model_id="auto", selection=_selection())

    assert resolution.workflow == "chat_v1"
    assert resolution.resolved_skills == []
    assert resolution.direct_capability == "get_weather"
    assert resolution.direct_capability_arguments == {"location": "杭州"}


@pytest.mark.asyncio
async def test_invalid_direct_tool_arguments_fail_closed_to_tool_free_chat():
    resolution = await _resolver(
        RouteGateway(
            SkillRouteProposal(
                route="direct",
                confidence=0.98,
                reason_code="needs_current_sources",
                direct_capability="get_weather",
                direct_capability_arguments={},
            )
        )
    ).resolve(query="今天天气", model_id="auto", selection=_selection())

    assert resolution.direct_capability is None
    assert resolution.selection_source == "fallback"
    assert resolution.reason_code == "invalid_direct_capability"


@pytest.mark.asyncio
async def test_confirmation_result_completes_without_skill_or_capability():
    gateway = RouteGateway(
        SkillRouteProposal(
            route="fortune",
            confidence=0.99,
            reason_code="fortune_request",
        )
    )

    class RejectCapabilities:
        async def execute(self, *args, **kwargs):
            raise AssertionError("confirmation must not execute a capability")

    application = LangGraphAgentApplication(
        gateway=gateway,
        capability_executor=RejectCapabilities(),
    )
    events = [
        event
        async for event in application.stream(
            RunCommand(
                execution_id="exec-confirmation",
                query="请看看我的命盘",
                messages=[],
                requested_workflow="default_llm_agent",
                selection=_selection(),
            )
        )
    ]

    assert [event.type for event in events] == [
        "route.selected",
        "confirmation.required",
        "answer.delta",
        "workflow.completed",
    ]
    route = events[0].data
    assert route["resolved_skills"] == []
    assert route["suggested_skill"] == "fortune"
    assert route["requires_confirmation"] is True

