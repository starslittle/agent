from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from ..gateway import ModelProviderError, StructuredOutputError
from ..types import (
    ModelMessage,
    ModelProfile,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventType,
    ModelToolCall,
    ModelUsage,
)


OutputT = TypeVar("OutputT", bound=BaseModel)


def _provider_error(exc: Exception) -> ModelProviderError:
    name = type(exc).__name__
    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, TimeoutError) or name in {
        "APITimeoutError",
        "TimeoutException",
    }:
        return ModelProviderError("timeout", retryable=True)
    if name in {"AuthenticationError", "PermissionDeniedError"}:
        return ModelProviderError("authentication_failed", retryable=False)
    if name == "RateLimitError" or status_code == 429:
        return ModelProviderError("rate_limited", retryable=True)
    if name in {"APIConnectionError", "ConnectError"}:
        return ModelProviderError("connection_failed", retryable=True)
    if name in {"BadRequestError", "UnprocessableEntityError"}:
        return ModelProviderError("invalid_request", retryable=False)
    return ModelProviderError(
        "upstream_failed",
        retryable=bool(status_code and int(status_code) >= 500),
    )


def _message_payload(message: ModelMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.name is not None:
        payload["name"] = message.name
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _usage(value: Any) -> ModelUsage:
    if value is None:
        return ModelUsage()
    details = getattr(value, "prompt_tokens_details", None)
    completion_details = getattr(value, "completion_tokens_details", None)
    return ModelUsage(
        input_tokens=int(getattr(value, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(value, "completion_tokens", 0) or 0),
        cached_tokens=int(getattr(details, "cached_tokens", 0) or 0),
        reasoning_tokens=int(
            getattr(completion_details, "reasoning_tokens", 0) or 0
        ),
        total_tokens=int(getattr(value, "total_tokens", 0) or 0),
    )


def _tool_calls(message: Any) -> list[ModelToolCall]:
    calls = []
    for item in getattr(message, "tool_calls", None) or []:
        function = getattr(item, "function", None)
        if function is None:
            continue
        calls.append(
            ModelToolCall(
                id=str(getattr(item, "id", "") or ""),
                name=str(getattr(function, "name", "") or ""),
                arguments=str(getattr(function, "arguments", "") or ""),
            )
        )
    return calls


def _strip_json_fence(content: str) -> str:
    value = content.strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class DashScopeOpenAIProvider:
    """Model Studio adapter using its official OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        client: Any | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("MODEL_BASE_URL is required")
        self._client = client or AsyncOpenAI(
            # Readiness rejects missing credentials before serving production
            # traffic. A non-secret sentinel keeps graph assembly import-safe.
            api_key=api_key or "not-configured",
            base_url=base_url,
        )

    @staticmethod
    def _request_kwargs(
        request: ModelRequest,
        profile: ModelProfile,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": profile.model,
            "messages": [_message_payload(item) for item in request.messages],
            "temperature": (
                request.temperature
                if request.temperature is not None
                else profile.temperature
            ),
            "extra_body": {**profile.extra_body, **request.extra_body},
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.tools:
            if not profile.capabilities.tool_calling:
                raise ValueError(
                    f"model profile {profile.name} does not support tool calling"
                )
            kwargs["tools"] = request.tools
            if request.tool_choice is not None:
                kwargs["tool_choice"] = request.tool_choice
            if request.parallel_tool_calls is not None:
                if not profile.capabilities.parallel_tool_calls:
                    raise ValueError(
                        f"model profile {profile.name} does not support "
                        "parallel tool calls"
                    )
                kwargs["parallel_tool_calls"] = request.parallel_tool_calls
        if request.response_format is not None:
            if not profile.capabilities.json_mode:
                raise ValueError(
                    f"model profile {profile.name} does not support JSON mode"
                )
            kwargs["response_format"] = request.response_format
        if not kwargs["extra_body"]:
            kwargs.pop("extra_body")
        return kwargs

    async def complete(
        self,
        request: ModelRequest,
        profile: ModelProfile,
    ) -> ModelResult:
        kwargs = self._request_kwargs(request, profile)
        try:
            response = await self._client.chat.completions.create(
                **kwargs,
                timeout=profile.timeout_seconds,
            )
        except ModelProviderError:
            raise
        except Exception as exc:
            raise _provider_error(exc) from exc
        choice = response.choices[0]
        message = choice.message
        return ModelResult(
            content=str(getattr(message, "content", "") or ""),
            model=str(getattr(response, "model", profile.model) or profile.model),
            finish_reason=getattr(choice, "finish_reason", None),
            usage=_usage(getattr(response, "usage", None)),
            tool_calls=_tool_calls(message),
            response_id=getattr(response, "id", None),
        )

    async def stream(
        self,
        request: ModelRequest,
        profile: ModelProfile,
    ) -> AsyncIterator[ModelStreamEvent]:
        if not profile.capabilities.streaming:
            raise ValueError(
                f"model profile {profile.name} does not support streaming"
            )
        kwargs = self._request_kwargs(request, profile)
        if profile.capabilities.stream_usage:
            kwargs["stream_options"] = {"include_usage": True}
        try:
            response = await self._client.chat.completions.create(
                **kwargs,
                stream=True,
                timeout=profile.timeout_seconds,
            )
        except ModelProviderError:
            raise
        except Exception as exc:
            raise _provider_error(exc) from exc
        last_model = profile.model
        response_id = None
        finish_reason = None
        usage = None
        async for chunk in response:
            last_model = str(getattr(chunk, "model", last_model) or last_model)
            response_id = getattr(chunk, "id", response_id)
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = _usage(chunk_usage)
                yield ModelStreamEvent(
                    type=ModelStreamEventType.USAGE,
                    model=last_model,
                    usage=usage,
                    response_id=response_id,
                )
            for choice in getattr(chunk, "choices", None) or []:
                reason = getattr(choice, "finish_reason", None)
                if reason is not None:
                    finish_reason = str(reason)
                text = str(getattr(getattr(choice, "delta", None), "content", "") or "")
                if text:
                    yield ModelStreamEvent(
                        type=ModelStreamEventType.DELTA,
                        text=text,
                        model=last_model,
                        response_id=response_id,
                    )
        yield ModelStreamEvent(
            type=ModelStreamEventType.COMPLETED,
            model=last_model,
            finish_reason=finish_reason,
            usage=usage,
            response_id=response_id,
        )

    async def structured(
        self,
        request: ModelRequest,
        profile: ModelProfile,
        output_type: type[OutputT],
    ) -> OutputT:
        if not profile.capabilities.json_mode:
            raise ValueError(
                f"model profile {profile.name} does not support JSON mode"
            )
        schema_instruction = (
            "Return only one valid JSON object matching this JSON Schema:\n"
            + json.dumps(output_type.model_json_schema(), ensure_ascii=False)
        )
        structured_request = request.model_copy(
            update={
                "messages": [
                    ModelMessage(role="system", content=schema_instruction),
                    *request.messages,
                ],
                "response_format": {"type": "json_object"},
                # Model Studio rejects JSON mode while thinking mode is active.
                # DeepSeek V4 enables thinking by default, so structured calls
                # must explicitly disable it at this provider boundary.
                "extra_body": {
                    **request.extra_body,
                    "enable_thinking": False,
                },
            }
        )
        result = await self.complete(structured_request, profile)
        try:
            return output_type.model_validate_json(
                _strip_json_fence(result.content)
            )
        except Exception as exc:
            raise StructuredOutputError(
                "model returned invalid structured output"
            ) from exc
