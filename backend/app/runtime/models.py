from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROTOCOL_VERSION = 1
TERMINAL_STATUSES = frozenset(
    {"completed", "cancelled", "failed", "timed_out"}
)


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


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    execution_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=128)
    agent_name: str = Field(default="default_llm_agent", max_length=128)
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


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1] = PROTOCOL_VERSION
    execution_id: str
    run_id: str
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=64)
    occurred_at: datetime
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
        return cls(
            execution_id=execution_id,
            run_id=run_id,
            sequence=sequence,
            type=event_type,
            occurred_at=datetime.now(timezone.utc),
            data=data or {},
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
