from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.capabilities import TARGET_CAPABILITY_SPECS
from agent.models import ModelCatalog, ModelMessage, ModelRequest
from agent.prompts.loader import load_prompt
from agent.skills import SkillRegistry, SkillSelection


RouteChoice = Literal["direct", "research", "fortune"]
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
    ) -> SkillRouteResolution:
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
            return self._direct(
                confidence=proposal.confidence,
                source="direct",
                reason_code=proposal.reason_code,
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
