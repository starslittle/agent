from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.skills.protocol import SelectionSource


PROTOCOL_VERSION = 1
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed", "timed_out"})


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    TIMED_OUT = "timed_out"

    @property
    def terminal(self) -> bool:
        return self.value in TERMINAL_STATUSES


ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.CANCEL_REQUESTED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.CANCEL_REQUESTED: frozenset(
        {
            RunStatus.CANCELLED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
        }
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.TIMED_OUT: frozenset(),
}


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return current == target or target in ALLOWED_TRANSITIONS[current]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=200_000)


class ContextSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(min_length=1, max_length=64)
    reference: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=500)


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(min_length=1, max_length=128)
    revision_id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=20_000)
    source: ContextSource
    updated_at: datetime


class ContextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_memory_proposals: bool = False


class ContextRequirementsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_mode: Literal["direct", "skill"]
    primary_skill: str | None = None
    purpose: str
    needs_personal_context: bool
    allowed_types: list[str]
    allowed_domains: list[str]
    item_budget: int = Field(ge=0, le=50)
    character_budget: int = Field(ge=0, le=50_000)


class ContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str = Field(min_length=1, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    purpose: str = Field(min_length=1, max_length=80)
    items: list[ContextItem] = Field(default_factory=list, max_length=50)
    policy: ContextPolicy
    requirements: ContextRequirementsPayload
    created_at: datetime | None = None


class AgentRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1] = PROTOCOL_VERSION
    execution_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    agent_name: str = Field(default="default_llm_agent", max_length=128)
    model_id: str = Field(default="auto", max_length=64)
    requested_skill: str | None = Field(default=None, max_length=64)
    query: str = Field(min_length=1, max_length=200_000)
    messages: list[ChatMessage] = Field(default_factory=list, max_length=200)


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    execution_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    agent_name: str = Field(default="default_llm_agent", max_length=128)
    model_id: str = Field(
        default="auto",
        pattern=r"^[a-z][a-z0-9_-]{0,63}$",
    )
    requested_skill: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    resolved_skills: list[str] = Field(default_factory=list, max_length=1)
    primary_skill: str | None = Field(default=None, max_length=64)
    selection_source: SelectionSource | None = None
    suggested_skill: str | None = Field(default=None, max_length=64)
    route_confidence: float | None = Field(default=None, ge=0, le=1)
    route_requires_confirmation: bool = False
    route_reason_code: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
    )
    context_package_id: str | None = Field(default=None, max_length=128)
    context_package: ContextPackage | None = None
    mode: str | None = Field(default=None, max_length=64)
    query: str = Field(min_length=1, max_length=200_000)
    messages: list[ChatMessage] = Field(default_factory=list, max_length=200)
    deadline_ms: int = Field(default=120_000, ge=1_000, le=900_000)
    shadow: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "execution_id",
        "run_id",
        "request_id",
        "idempotency_key",
        "conversation_id",
        "agent_name",
        "model_id",
    )
    @classmethod
    def strip_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identifier cannot be blank")
        return stripped

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query cannot be blank")
        return stripped

    @field_validator(
        "requested_skill",
        "primary_skill",
        "suggested_skill",
        "context_package_id",
    )
    @classmethod
    def strip_optional_identifiers(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("optional identifier cannot be blank")
        return stripped

    @field_validator("resolved_skills")
    @classmethod
    def validate_resolved_skills(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 64 for value in normalized):
            raise ValueError("resolved skill ids must be non-empty and bounded")
        if len(set(normalized)) != len(normalized):
            raise ValueError("resolved skill ids must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_skill_projection(self) -> "AgentRunRequest":
        expected_primary = self.resolved_skills[0] if self.resolved_skills else None
        if self.primary_skill != expected_primary:
            raise ValueError("primary_skill must match resolved_skills")
        if self.selection_source is not None and not self.resolved_skills:
            if self.selection_source not in {"direct", "fallback", "automatic"}:
                raise ValueError("empty skill resolution requires direct or fallback")
        if self.route_requires_confirmation:
            if (
                self.selection_source != "automatic"
                or self.resolved_skills
                or self.suggested_skill is None
            ):
                raise ValueError("invalid confirmation-only skill resolution")
        if self.context_package is not None:
            if self.context_package_id != self.context_package.package_id:
                raise ValueError("context package id mismatch")
            if self.context_package.run_id not in {None, self.run_id}:
                raise ValueError("context package run mismatch")
            if self.route_reason_code is None or self.selection_source is None:
                raise ValueError("frozen context requires frozen resolution")
        return self


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    execution_id: str
    run_id: str
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
    trace_id: str = ""
    span_id: str | None = None
    parent_span_id: str | None = None
    category: str = "runtime"
    stage: str | None = None
    event_schema_version: int = 1
    content_capture_level: Literal["off", "hashed", "sampled"] = "hashed"
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        execution_id: str,
        run_id: str,
        sequence: int,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> "AgentEvent":
        event_data = data or {}
        category = event_type.split(".", 1)[0]
        return cls(
            execution_id=execution_id,
            run_id=run_id,
            sequence=sequence,
            type=event_type,
            occurred_at=datetime.now(timezone.utc),
            trace_id=execution_id,
            span_id=event_data.get("span_id"),
            parent_span_id=event_data.get("parent_span_id"),
            category=category,
            stage=event_data.get("stage"),
            content_capture_level=event_data.get(
                "content_capture_level",
                "hashed",
            ),
            data=event_data,
        )

    @property
    def sse_id(self) -> str:
        return f"{self.execution_id}:{self.sequence}"


class RunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    service_version: str
    execution_id: str
    run_id: str
    status: RunStatus
    last_sequence: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime
    error: dict[str, Any] | None = None
