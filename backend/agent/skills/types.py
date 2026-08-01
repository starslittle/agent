from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Identifier = str


class SkillModelRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    streaming: bool
    structured_output: bool
    tool_calling: bool


class SkillBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deadline_seconds: int = Field(gt=0, le=900)
    max_model_calls: int = Field(gt=0, le=64)
    max_tool_calls: int = Field(gt=0, le=64)


class SkillRiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["low", "medium", "high"]
    explicit_confirmation: Literal["never", "contextual", "always"]


class SkillMemoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    may_propose_updates: bool
    may_commit_updates: bool

    @model_validator(mode="after")
    def reject_commit_without_proposal(self) -> "SkillMemoryPolicy":
        if self.may_commit_updates and not self.may_propose_updates:
            raise ValueError("memory commits require update proposals")
        return self


class SkillUI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(pattern=r"^/[a-z][a-z0-9_-]{0,63}$")
    visible: bool


class SkillPublicDescription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=1_000)
    context_scope: list[
        Literal["confirmed_fact", "current_state", "personal_rule", "ai_analysis"]
    ] = Field(max_length=8)
    confirmation_summary: str = Field(min_length=1, max_length=1_000)

    @field_validator("context_scope")
    @classmethod
    def validate_context_scope(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("public context scope must be unique")
        return values


class SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    version: int = Field(gt=0, le=2_147_483_647)
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1_000)
    workflow: str = Field(pattern=r"^[a-z][a-z0-9_]{0,127}$")
    input_schema: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,127}$")
    output_schema: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,127}$")
    allowed_capabilities: list[str] = Field(min_length=1, max_length=64)
    model_requirements: SkillModelRequirements
    budgets: SkillBudgets
    risk: SkillRiskPolicy
    memory: SkillMemoryPolicy
    ui: SkillUI
    public: SkillPublicDescription
    available: bool

    @field_validator("allowed_capabilities")
    @classmethod
    def validate_capabilities(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 128 for value in values):
            raise ValueError("capability names must be non-empty and bounded")
        if len(set(values)) != len(values):
            raise ValueError("allowed capabilities must be unique")
        return values


class SkillManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[SkillManifest] = Field(min_length=1, max_length=128)
