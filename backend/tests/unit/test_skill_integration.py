from __future__ import annotations

import pytest

from agent.application import LangGraphAgentApplication, RunCommand
from agent.models.factory import default_model_profiles
from agent.skills import get_skill_registry, resolve_compatible_selection


class ProfileOnlyGateway:
    def profile(self, profile_name):
        return {
            profile.name: profile for profile in default_model_profiles()
        }[profile_name]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_skill", "legacy_agent", "source"),
    [
        ("research", "default_llm_agent", "user"),
        ("fortune", "default_llm_agent", "user"),
        (None, "research_agent", "compatibility"),
        (None, "fortune_agent", "compatibility"),
    ],
)
async def test_skill_manifest_drives_frozen_execution_snapshot(
    requested_skill,
    legacy_agent,
    source,
):
    registry = get_skill_registry()
    selection = resolve_compatible_selection(
        requested_skill=requested_skill,
        agent_name=legacy_agent,
        registry=registry,
    )
    application = LangGraphAgentApplication(
        gateway=ProfileOnlyGateway(),
        skill_registry=registry,
    )
    command = await application.resolve_command(
        RunCommand(
            execution_id="exec-skill-snapshot",
            query="执行已选择的专业能力",
            messages=[],
            requested_workflow=selection.agent_name,
            selection=selection,
        )
    )
    provenance = application.describe_provenance(
        command.requested_workflow,
        model_id=command.model_id,
        selection=command.selection,
        resolution=command.resolution,
    )
    skill = registry.resolve(command.resolution.primary_skill)

    assert provenance["selection_source"] == source
    assert provenance["workflow_name"] == skill.workflow
    assert provenance["skill_snapshot"]["version"] == skill.version
    assert provenance["skill_snapshot"]["budgets"] == skill.budgets.model_dump()
    assert {
        capability["name"] for capability in provenance["capabilities"]
    } == set(skill.allowed_capabilities)
    assert provenance["model_snapshot"]["execution_profile"] == (
        "default_reasoning"
    )


@pytest.mark.asyncio
async def test_direct_answer_has_no_skill_or_capability_snapshot():
    selection = resolve_compatible_selection(
        requested_skill=None,
        agent_name="default_llm_agent",
    )

    class DirectResolver:
        async def resolve(self, **kwargs):
            from agent.root import SkillRouteResolution

            return SkillRouteResolution(
                requested_skill=None,
                resolved_skills=[],
                primary_skill=None,
                confidence=0.95,
                selection_source="direct",
                requires_confirmation=False,
                reason_code="general_conversation",
                agent_name="default_llm_agent",
                workflow="chat_v1",
            )

    application = LangGraphAgentApplication(
        gateway=ProfileOnlyGateway(),
        skill_resolver=DirectResolver(),
    )
    command = await application.resolve_command(
        RunCommand(
            execution_id="exec-direct-snapshot",
            query="你好",
            messages=[],
            requested_workflow="default_llm_agent",
            selection=selection,
        )
    )
    provenance = application.describe_provenance(
        command.requested_workflow,
        selection=command.selection,
        resolution=command.resolution,
    )

    assert provenance["resolved_skills"] == []
    assert provenance["skill_snapshot"] is None
    assert provenance["capabilities"] == []
