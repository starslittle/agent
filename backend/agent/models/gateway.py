from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Callable, Protocol, TypeVar

from pydantic import BaseModel

from app.observability import new_span_id, payload_fingerprint

from .types import (
    ModelMessage,
    ModelProfile,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelStreamEventType,
)


OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelProvider(Protocol):
    async def complete(
        self,
        request: ModelRequest,
        profile: ModelProfile,
    ) -> ModelResult: ...

    def stream(
        self,
        request: ModelRequest,
        profile: ModelProfile,
    ) -> AsyncIterator[ModelStreamEvent]: ...

    async def structured(
        self,
        request: ModelRequest,
        profile: ModelProfile,
        output_type: type[OutputT],
    ) -> OutputT: ...


class UnknownModelProfileError(LookupError):
    pass


class UnknownModelProviderError(LookupError):
    pass


class ModelProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(f"model provider request failed: {code}")
        self.code = code
        self.retryable = retryable


class StructuredOutputError(RuntimeError):
    pass


class ModelGateway:
    def __init__(
        self,
        *,
        profiles: list[ModelProfile],
        providers: dict[str, ModelProvider],
    ) -> None:
        self._profiles = {profile.name: profile for profile in profiles}
        self._providers = dict(providers)
        if len(self._profiles) != len(profiles):
            raise ValueError("model profile names must be unique")

    def profile(self, profile_name: str) -> ModelProfile:
        try:
            return self._profiles[profile_name]
        except KeyError as exc:
            raise UnknownModelProfileError(profile_name) from exc

    def _resolve(self, profile_name: str) -> tuple[ModelProvider, ModelProfile]:
        profile = self.profile(profile_name)
        try:
            provider = self._providers[profile.provider]
        except KeyError as exc:
            raise UnknownModelProviderError(profile.provider) from exc
        return provider, profile

    async def complete(
        self,
        profile_name: str,
        request: ModelRequest,
    ) -> ModelResult:
        provider, profile = self._resolve(profile_name)
        return await provider.complete(request, profile)

    async def stream(
        self,
        profile_name: str,
        request: ModelRequest,
    ) -> AsyncIterator[ModelStreamEvent]:
        provider, profile = self._resolve(profile_name)
        async for event in provider.stream(request, profile):
            yield event

    async def structured(
        self,
        profile_name: str,
        request: ModelRequest,
        output_type: type[OutputT],
    ) -> OutputT:
        provider, profile = self._resolve(profile_name)
        attempts = max(1, min(profile.max_retries + 1, 3))
        current_request = request
        for attempt in range(1, attempts + 1):
            try:
                return await provider.structured(
                    current_request,
                    profile,
                    output_type,
                )
            except StructuredOutputError:
                if attempt >= attempts:
                    raise
                current_request = current_request.model_copy(
                    update={
                        "messages": [
                            *current_request.messages,
                            ModelMessage(
                                role="system",
                                content=(
                                    "The previous response did not match the "
                                    "required JSON Schema. Return exactly one "
                                    "valid JSON object and no prose."
                                ),
                            ),
                        ]
                    }
                )
        raise AssertionError("unreachable structured retry state")


ModelEventSink = Callable[[str, dict[str, Any]], None]


class ObservedModelGateway:
    """Run-scoped middleware around any ModelGateway-compatible object."""

    def __init__(self, delegate, event_sink: ModelEventSink) -> None:
        self._delegate = delegate
        self._event_sink = event_sink

    def profile(self, profile_name: str) -> ModelProfile:
        return self._delegate.profile(profile_name)

    def _base(
        self,
        profile_name: str,
        request: ModelRequest,
        stage: str,
    ) -> dict[str, Any]:
        return {
            "span_id": new_span_id(),
            "span_type": "model",
            "stage": stage,
            "model_profile": profile_name,
            "content_capture_level": "hashed",
            "input": payload_fingerprint(
                {
                    "messages": [
                        {
                            "role": item.role,
                            "content": item.content,
                        }
                        for item in request.messages
                    ],
                    "tools": request.tools,
                }
            ),
        }

    async def complete(
        self,
        profile_name: str,
        request: ModelRequest,
        *,
        stage: str,
    ) -> ModelResult:
        base = self._base(profile_name, request, stage)
        self._event_sink("model.started", base)
        started_at = time.perf_counter()
        try:
            result = await self._delegate.complete(profile_name, request)
        except Exception as exc:
            self._event_sink(
                "model.failed",
                {
                    **base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "error_code": type(exc).__name__[:128],
                },
            )
            raise
        self._emit_completed(base, result, started_at)
        return result

    async def structured(
        self,
        profile_name: str,
        request: ModelRequest,
        output_type: type[OutputT],
        *,
        stage: str,
    ) -> OutputT:
        base = {
            **self._base(profile_name, request, stage),
            "output_schema": output_type.__name__,
        }
        self._event_sink("model.started", base)
        started_at = time.perf_counter()
        try:
            result = await self._delegate.structured(
                profile_name,
                request,
                output_type,
            )
        except Exception as exc:
            self._event_sink(
                "model.failed",
                {
                    **base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "error_code": type(exc).__name__[:128],
                },
            )
            raise
        self._event_sink(
            "model.completed",
            {
                **base,
                "duration_ms": int(
                    (time.perf_counter() - started_at) * 1000
                ),
            },
        )
        return result

    async def stream(
        self,
        profile_name: str,
        request: ModelRequest,
        *,
        stage: str,
    ) -> AsyncIterator[ModelStreamEvent]:
        base = self._base(profile_name, request, stage)
        self._event_sink("model.started", base)
        started_at = time.perf_counter()
        completed = None
        try:
            async for event in self._delegate.stream(
                profile_name,
                request,
            ):
                if (
                    event.type == ModelStreamEventType.USAGE
                    and event.usage is not None
                ):
                    self._event_sink(
                        "usage",
                        {
                            **event.usage.model_dump(),
                            "stage": stage,
                            "model_name": event.model,
                        },
                    )
                completed = event
                yield event
        except Exception as exc:
            self._event_sink(
                "model.failed",
                {
                    **base,
                    "duration_ms": int(
                        (time.perf_counter() - started_at) * 1000
                    ),
                    "error_code": type(exc).__name__[:128],
                },
            )
            raise
        self._event_sink(
            "model.completed",
            {
                **base,
                "duration_ms": int(
                    (time.perf_counter() - started_at) * 1000
                ),
                "model_name": getattr(completed, "model", ""),
                "finish_reason": getattr(
                    completed,
                    "finish_reason",
                    None,
                ),
            },
        )

    def _emit_completed(
        self,
        base: dict[str, Any],
        result: ModelResult,
        started_at: float,
    ) -> None:
        self._event_sink(
            "usage",
            {
                **result.usage.model_dump(),
                "stage": base["stage"],
                "model_name": result.model,
            },
        )
        self._event_sink(
            "model.completed",
            {
                **base,
                "duration_ms": int(
                    (time.perf_counter() - started_at) * 1000
                ),
                "model_name": result.model,
                "finish_reason": result.finish_reason,
            },
        )
