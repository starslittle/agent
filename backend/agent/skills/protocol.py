from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .registry import SkillRegistry, get_skill_registry


SelectionSource = Literal["direct", "user", "compatibility", "automatic", "fallback"]

LEGACY_AGENT_SKILLS: dict[str, str | None] = {
    "default": None,
    "default_llm_agent": None,
    "chat": None,
    "chat_v1": None,
    "research": "research",
    "research_agent": "research",
    "research_v1": "research",
    "general_rag_agent": "research",
    "fortune": "fortune",
    "fortune_agent": "fortune",
    "fortune_v1": "fortune",
}

SKILL_AGENT_NAMES = {
    "research": "research_agent",
    "fortune": "fortune_agent",
}


class SkillSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_skill: str | None = None
    resolved_skills: list[str] = Field(max_length=1)
    primary_skill: str | None = None
    selection_source: SelectionSource
    agent_name: str
    workflow: str
    skill_version: int | None = None


class UnknownRequestedSkillError(LookupError):
    code = "unknown_requested_skill"

    def __init__(self, skill_id: str) -> None:
        super().__init__(f"unknown requested_skill: {skill_id}")
        self.skill_id = skill_id


class ConflictingSkillRequestError(ValueError):
    code = "conflicting_skill_request"


def _available_skill(skill_id: str, registry: SkillRegistry):
    try:
        skill = registry.resolve(skill_id)
    except LookupError as exc:
        raise UnknownRequestedSkillError(skill_id) from exc
    if not skill.available:
        raise UnknownRequestedSkillError(skill_id)
    return skill


def resolve_compatible_selection(
    *,
    requested_skill: str | None,
    agent_name: str | None,
    registry: SkillRegistry | None = None,
) -> SkillSelection:
    skill_registry = registry or get_skill_registry()
    normalized_agent = (agent_name or "default_llm_agent").strip()
    explicit = requested_skill.strip() if requested_skill is not None else None

    if explicit is not None:
        skill = _available_skill(explicit, skill_registry)
        expected_agent = SKILL_AGENT_NAMES.get(explicit)
        if expected_agent is None:
            raise UnknownRequestedSkillError(explicit)
        compatible_agents = {"", "default_llm_agent", expected_agent, explicit, skill.workflow}
        if normalized_agent not in compatible_agents:
            raise ConflictingSkillRequestError(
                "requested_skill conflicts with legacy agent_name"
            )
        selection_source: SelectionSource = (
            "user"
            if normalized_agent in {"", "default_llm_agent", explicit}
            else "compatibility"
        )
        return SkillSelection(
            requested_skill=explicit,
            resolved_skills=[explicit],
            primary_skill=explicit,
            selection_source=selection_source,
            agent_name=expected_agent,
            workflow=skill.workflow,
            skill_version=skill.version,
        )

    if normalized_agent not in LEGACY_AGENT_SKILLS:
        raise ConflictingSkillRequestError("unknown legacy agent_name")
    compatible_skill = LEGACY_AGENT_SKILLS[normalized_agent]
    if compatible_skill is None:
        return SkillSelection(
            requested_skill=None,
            resolved_skills=[],
            primary_skill=None,
            selection_source="direct",
            agent_name="default_llm_agent",
            workflow="chat_v1",
        )
    skill = _available_skill(compatible_skill, skill_registry)
    return SkillSelection(
        requested_skill=compatible_skill,
        resolved_skills=[compatible_skill],
        primary_skill=compatible_skill,
        selection_source="compatibility",
        agent_name=SKILL_AGENT_NAMES[compatible_skill],
        workflow=skill.workflow,
        skill_version=skill.version,
    )
