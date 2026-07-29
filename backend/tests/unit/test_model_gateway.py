from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agent.models import (
    ModelCapabilities,
    ModelGateway,
    ModelMessage,
    ModelProfile,
    ModelProviderError,
    ModelRequest,
    ModelStreamEventType,
    StructuredOutputError,
    UnknownModelProfileError,
)
from agent.models.providers import DashScopeOpenAIProvider


class _AsyncChunks:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._iterator = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _client(*responses):
    completions = _FakeCompletions(responses)
    return (
        SimpleNamespace(chat=SimpleNamespace(completions=completions)),
        completions,
    )


def _profile(**capability_overrides):
    capabilities = ModelCapabilities(
        streaming=True,
        tool_calling=True,
        parallel_tool_calls=True,
        json_mode=True,
        stream_usage=True,
    ).model_copy(update=capability_overrides)
    return ModelProfile(
        name="reasoning",
        provider="dashscope_openai",
        model="deepseek-v4-flash",
        temperature=0.1,
        capabilities=capabilities,
    )


@pytest.mark.asyncio
async def test_openai_compatible_provider_normalizes_completion_and_usage():
    response = SimpleNamespace(
        id="response-1",
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="你好", tool_calls=[]),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=3,
            total_tokens=15,
            prompt_tokens_details=SimpleNamespace(cached_tokens=2),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=1),
        ),
    )
    client, completions = _client(response)
    provider = DashScopeOpenAIProvider(
        api_key="unused-in-test",
        base_url="https://example.invalid/compatible-mode/v1",
        client=client,
    )

    result = await provider.complete(
        ModelRequest(
            messages=[ModelMessage(role="user", content="你好")],
        ),
        _profile(),
    )

    assert result.content == "你好"
    assert result.response_id == "response-1"
    assert result.usage.model_dump() == {
        "input_tokens": 12,
        "output_tokens": 3,
        "cached_tokens": 2,
        "reasoning_tokens": 1,
        "total_tokens": 15,
    }
    assert completions.calls[0]["model"] == "deepseek-v4-flash"
    assert completions.calls[0]["messages"] == [
        {"role": "user", "content": "你好"}
    ]
    assert "api_key" not in completions.calls[0]


@pytest.mark.asyncio
async def test_openai_compatible_provider_normalizes_stream_and_final_usage():
    stream = _AsyncChunks(
        [
            SimpleNamespace(
                id="response-2",
                model="deepseek-v4-flash",
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(content="你"),
                    )
                ],
            ),
            SimpleNamespace(
                id="response-2",
                model="deepseek-v4-flash",
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        delta=SimpleNamespace(content="好"),
                    )
                ],
            ),
            SimpleNamespace(
                id="response-2",
                model="deepseek-v4-flash",
                usage=SimpleNamespace(
                    prompt_tokens=4,
                    completion_tokens=2,
                    total_tokens=6,
                    prompt_tokens_details=None,
                    completion_tokens_details=None,
                ),
                choices=[],
            ),
        ]
    )
    client, completions = _client(stream)
    provider = DashScopeOpenAIProvider(
        api_key="unused-in-test",
        base_url="https://example.invalid/compatible-mode/v1",
        client=client,
    )

    events = [
        event
        async for event in provider.stream(
            ModelRequest(
                messages=[ModelMessage(role="user", content="你好")],
            ),
            _profile(),
        )
    ]

    assert [event.type for event in events] == [
        ModelStreamEventType.DELTA,
        ModelStreamEventType.DELTA,
        ModelStreamEventType.USAGE,
        ModelStreamEventType.COMPLETED,
    ]
    assert "".join(event.text for event in events) == "你好"
    assert events[-1].finish_reason == "stop"
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 6
    assert completions.calls[0]["stream"] is True
    assert completions.calls[0]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_structured_output_uses_json_mode_and_validates_schema():
    class Decision(BaseModel):
        route: str

    response = SimpleNamespace(
        id="response-json",
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content='```json\n{"route":"research"}\n```',
                    tool_calls=[],
                ),
            )
        ],
        usage=None,
    )
    client, completions = _client(response)
    provider = DashScopeOpenAIProvider(
        api_key="unused-in-test",
        base_url="https://example.invalid/compatible-mode/v1",
        client=client,
    )

    result = await provider.structured(
        ModelRequest(
            messages=[ModelMessage(role="user", content="选择路由")],
        ),
        _profile(),
        Decision,
    )

    assert result == Decision(route="research")
    call = completions.calls[0]
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"enable_thinking": False}
    assert call["messages"][0]["role"] == "system"
    assert "JSON Schema" in call["messages"][0]["content"]


@pytest.mark.asyncio
async def test_gateway_resolves_profile_and_rejects_unknown_profile():
    class FakeProvider:
        async def complete(self, request, profile):
            return SimpleNamespace(content=f"{profile.name}:{request.messages[0].content}")

    gateway = ModelGateway(
        profiles=[_profile()],
        providers={"dashscope_openai": FakeProvider()},
    )
    request = ModelRequest(
        messages=[ModelMessage(role="user", content="hello")]
    )

    result = await gateway.complete("reasoning", request)
    assert result.content == "reasoning:hello"

    with pytest.raises(UnknownModelProfileError):
        await gateway.complete("missing", request)


@pytest.mark.asyncio
async def test_profile_capabilities_are_enforced_before_provider_call():
    client, completions = _client()
    provider = DashScopeOpenAIProvider(
        api_key="unused-in-test",
        base_url="https://example.invalid/compatible-mode/v1",
        client=client,
    )
    request = ModelRequest(
        messages=[ModelMessage(role="user", content="hello")],
        tools=[{"type": "function", "function": {"name": "search"}}],
    )

    with pytest.raises(ValueError, match="does not support tool calling"):
        await provider.complete(
            request,
            _profile(tool_calling=False),
        )
    assert completions.calls == []


@pytest.mark.asyncio
async def test_provider_errors_are_mapped_without_leaking_upstream_details():
    client, _ = _client()

    async def fail(**kwargs):
        raise TimeoutError("secret provider response body")

    client.chat.completions.create = fail
    provider = DashScopeOpenAIProvider(
        api_key="unused-in-test",
        base_url="https://example.invalid/compatible-mode/v1",
        client=client,
    )

    with pytest.raises(ModelProviderError) as captured:
        await provider.complete(
            ModelRequest(
                messages=[ModelMessage(role="user", content="hello")],
            ),
            _profile(),
        )

    assert captured.value.code == "timeout"
    assert captured.value.retryable is True
    assert "secret" not in str(captured.value)


@pytest.mark.asyncio
async def test_gateway_repairs_structured_output_with_a_bounded_retry():
    class Decision(BaseModel):
        route: str

    class RepairingProvider:
        def __init__(self):
            self.requests = []

        async def structured(self, request, profile, output_type):
            self.requests.append(request)
            if len(self.requests) == 1:
                raise StructuredOutputError("invalid")
            return output_type(route="research")

    provider = RepairingProvider()
    gateway = ModelGateway(
        profiles=[_profile()],
        providers={"dashscope_openai": provider},
    )
    result = await gateway.structured(
        "reasoning",
        ModelRequest(
            messages=[ModelMessage(role="user", content="选择路由")]
        ),
        Decision,
    )

    assert result == Decision(route="research")
    assert len(provider.requests) == 2
    repair = provider.requests[1].messages[-1]
    assert repair.role == "system"
    assert "valid JSON object" in repair.content
