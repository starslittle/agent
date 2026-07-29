from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


JsonObject = dict[str, Any]
MessageRole = Literal["system", "user", "assistant", "tool"]


class ModelStreamEventType(StrEnum):
    DELTA = "delta"
    USAGE = "usage"
    COMPLETED = "completed"


class ModelMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class ModelCapabilities(BaseModel):
    streaming: bool = True
    tool_calling: bool = False
    parallel_tool_calls: bool = False
    json_mode: bool = False
    strict_json_schema: bool = False
    stream_usage: bool = False


class ModelProfile(BaseModel):
    name: str
    provider: str
    model: str
    temperature: float = Field(default=0.2, ge=0, le=2)
    timeout_seconds: float = Field(default=120, gt=0)
    max_retries: int = Field(default=2, ge=0, le=8)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    extra_body: JsonObject = Field(default_factory=dict)


class ModelRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=False)

    messages: list[ModelMessage]
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    tools: list[JsonObject] = Field(default_factory=list)
    tool_choice: str | JsonObject | None = None
    parallel_tool_calls: bool | None = None
    response_format: JsonObject | None = None
    extra_body: JsonObject = Field(default_factory=dict)


class ModelToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class ModelUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


class ModelResult(BaseModel):
    content: str = ""
    model: str = ""
    finish_reason: str | None = None
    usage: ModelUsage = Field(default_factory=ModelUsage)
    tool_calls: list[ModelToolCall] = Field(default_factory=list)
    response_id: str | None = None


class ModelStreamEvent(BaseModel):
    type: ModelStreamEventType
    text: str = ""
    model: str = ""
    finish_reason: str | None = None
    usage: ModelUsage | None = None
    response_id: str | None = None
