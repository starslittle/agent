from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.capabilities import TARGET_CAPABILITY_SPECS
from agent.models import ModelCatalog, ModelMessage, ModelRequest
from agent.prompts.loader import load_prompt
from agent.skills import SkillRegistry, SkillSelection


RouteChoice = Literal["direct", "research", "fortune"]
DirectCapability = Literal["get_current_date", "get_weather", "web_search"]
PublicRouteReason = Literal[
    "general_conversation",
    "needs_current_sources",
    "fortune_request",
    "ambiguous_intent",
]

LOW_CONFIDENCE = 0.55
HIGH_CONFIDENCE = 0.85
ROUTE_PROMPT_PATH = "agent/prompts/skill_route_v1.txt"


class SkillRouteProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: RouteChoice
    confidence: float = Field(ge=0, le=1)
    reason_code: PublicRouteReason
    direct_capability: DirectCapability | None = None
    direct_capability_arguments: dict[str, Any] = Field(default_factory=dict)


class SkillRouteResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_skill: str | None
    resolved_skills: list[str] = Field(max_length=1)
    primary_skill: str | None
    suggested_skill: str | None = None
    confidence: float = Field(ge=0, le=1)
    selection_source: Literal[
        "direct", "user", "compatibility", "automatic", "fallback"
    ]
    requires_confirmation: bool
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    agent_name: str
    workflow: str
    skill_version: int | None = None
    direct_capability: DirectCapability | None = None
    direct_capability_arguments: dict[str, Any] = Field(default_factory=dict)

    def as_selection(self) -> SkillSelection:
        return SkillSelection(
            requested_skill=self.requested_skill,
            resolved_skills=self.resolved_skills,
            primary_skill=self.primary_skill,
            selection_source=self.selection_source,
            agent_name=self.agent_name,
            workflow=self.workflow,
            skill_version=self.skill_version,
        )


class ContextRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    execution_mode: Literal["direct", "skill"]
    primary_skill: str | None
    purpose: str
    needs_personal_context: bool
    allowed_types: list[str]
    allowed_domains: list[str]
    item_budget: int = Field(ge=0, le=50)
    character_budget: int = Field(ge=0, le=50_000)


def context_requirements_for(resolution: SkillRouteResolution) -> ContextRequirements:
    if resolution.requires_confirmation:
        return ContextRequirements(
            execution_mode="direct",
            primary_skill=None,
            purpose="skill_confirmation",
            needs_personal_context=False,
            allowed_types=[],
            allowed_domains=[],
            item_budget=0,
            character_budget=0,
        )
    if resolution.primary_skill == "fortune":
        return ContextRequirements(
            execution_mode="skill",
            primary_skill="fortune",
            purpose="fortune",
            needs_personal_context=True,
            allowed_types=["confirmed_fact", "current_state", "personal_rule"],
            allowed_domains=["fortune", "profile"],
            item_budget=6,
            character_budget=2400,
        )
    if resolution.primary_skill == "research":
        return ContextRequirements(
            execution_mode="skill",
            primary_skill="research",
            purpose="research",
            needs_personal_context=True,
            allowed_types=["confirmed_fact", "current_state", "personal_rule"],
            allowed_domains=[],
            item_budget=8,
            character_budget=4000,
        )
    return ContextRequirements(
        execution_mode="direct",
        primary_skill=None,
        purpose="conversation",
        needs_personal_context=True,
        allowed_types=["confirmed_fact", "current_state", "personal_rule"],
        allowed_domains=[],
        item_budget=6,
        character_budget=2400,
    )


class SkillPolicyError(PermissionError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RootSkillResolver:
    def __init__(
        self,
        *,
        gateway,
        skill_registry: SkillRegistry,
        model_catalog: ModelCatalog,
        allowed_skill_ids: set[str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._skills = skill_registry
        self._models = model_catalog
        self._allowed_skill_ids = (
            set(allowed_skill_ids)
            if allowed_skill_ids is not None
            else {skill.id for skill in skill_registry.available()}
        )

    def _validate_skill(self, skill_id: str, model_id: str):
        skill = self._skills.resolve(skill_id)
        if not skill.available:
            raise SkillPolicyError("skill_unavailable")
        if skill_id not in self._allowed_skill_ids:
            raise SkillPolicyError("skill_not_allowed")
        if any(
            capability not in TARGET_CAPABILITY_SPECS
            for capability in skill.allowed_capabilities
        ):
            raise SkillPolicyError("skill_capability_unavailable")

        model = self._models.resolve(model_id)
        capabilities = model.capabilities
        requirements = skill.model_requirements
        if requirements.streaming and not capabilities.streaming:
            raise SkillPolicyError("model_capability_missing")
        if requirements.tool_calling and not capabilities.tool_calling:
            raise SkillPolicyError("model_capability_missing")
        if requirements.structured_output and not (
            capabilities.json_mode or capabilities.strict_json_schema
        ):
            raise SkillPolicyError("model_capability_missing")
        return skill

    def _direct(
        self,
        *,
        confidence: float,
        source: Literal["direct", "fallback"],
        reason_code: str,
        capability: DirectCapability | None = None,
        capability_arguments: dict[str, Any] | None = None,
    ) -> SkillRouteResolution:
        normalized_arguments: dict[str, Any] = {}
        if capability is not None:
            spec = TARGET_CAPABILITY_SPECS[capability]
            normalized_arguments = spec.input_type.model_validate(
                capability_arguments or {}
            ).model_dump(exclude_none=True)
        return SkillRouteResolution(
            requested_skill=None,
            resolved_skills=[],
            primary_skill=None,
            confidence=confidence,
            selection_source=source,
            requires_confirmation=False,
            reason_code=reason_code,
            agent_name="default_llm_agent",
            workflow="chat_v1",
            direct_capability=capability,
            direct_capability_arguments=normalized_arguments,
        )

    async def resolve(
        self,
        *,
        query: str,
        model_id: str,
        selection: SkillSelection,
    ) -> SkillRouteResolution:
        normalized_query = query.strip()
        if not normalized_query or len(normalized_query) > 200_000:
            raise SkillPolicyError("invalid_skill_input")

        if selection.primary_skill is not None:
            skill = self._validate_skill(selection.primary_skill, model_id)
            return SkillRouteResolution(
                requested_skill=selection.requested_skill,
                resolved_skills=[skill.id],
                primary_skill=skill.id,
                confidence=1,
                selection_source=selection.selection_source,
                requires_confirmation=False,
                reason_code=(
                    "legacy_compatibility"
                    if selection.selection_source == "compatibility"
                    else "explicit_skill"
                ),
                agent_name=selection.agent_name,
                workflow=skill.workflow,
                skill_version=skill.version,
            )

        model = self._models.resolve(model_id)
        try:
            proposal = await self._gateway.structured(
                model.profile,
                ModelRequest(
                    messages=[
                        ModelMessage(
                            role="system",
                            content=load_prompt(ROUTE_PROMPT_PATH),
                        ),
                        ModelMessage(role="user", content=normalized_query),
                    ],
                    temperature=0,
                    max_tokens=120,
                ),
                SkillRouteProposal,
            )
        except Exception:
            return self._direct(
                confidence=0,
                source="fallback",
                reason_code="route_model_failed",
            )

        if proposal.route == "direct":
            try:
                return self._direct(
                    confidence=proposal.confidence,
                    source="direct",
                    reason_code=proposal.reason_code,
                    capability=proposal.direct_capability,
                    capability_arguments=proposal.direct_capability_arguments,
                )
            except (KeyError, ValueError):
                return self._direct(
                    confidence=proposal.confidence,
                    source="fallback",
                    reason_code="invalid_direct_capability",
                )
        if proposal.confidence < LOW_CONFIDENCE:
            return self._direct(
                confidence=proposal.confidence,
                source="fallback",
                reason_code="low_confidence_direct",
            )

        try:
            skill = self._validate_skill(proposal.route, model_id)
        except (LookupError, SkillPolicyError):
            return self._direct(
                confidence=proposal.confidence,
                source="fallback",
                reason_code="automatic_skill_unavailable",
            )

        requires_confirmation = (
            proposal.confidence < HIGH_CONFIDENCE or skill.id == "fortune"
        )
        if requires_confirmation:
            return SkillRouteResolution(
                requested_skill=None,
                resolved_skills=[],
                primary_skill=None,
                suggested_skill=skill.id,
                confidence=proposal.confidence,
                selection_source="automatic",
                requires_confirmation=True,
                reason_code="automatic_confirmation_required",
                agent_name="default_llm_agent",
                workflow="chat_v1",
            )

        return SkillRouteResolution(
            requested_skill=None,
            resolved_skills=[skill.id],
            primary_skill=skill.id,
            confidence=proposal.confidence,
            selection_source="automatic",
            requires_confirmation=False,
            reason_code=proposal.reason_code,
            agent_name=(
                "research_agent" if skill.id == "research" else "fortune_agent"
            ),
            workflow=skill.workflow,
            skill_version=skill.version,
        )
