from __future__ import annotations

from functools import lru_cache

from app.core.settings import settings

from .gateway import ModelGateway
from .providers import DashScopeOpenAIProvider
from .types import ModelCapabilities, ModelProfile


def default_model_profiles() -> list[ModelProfile]:
    capabilities = ModelCapabilities(
        streaming=True,
        tool_calling=True,
        parallel_tool_calls=True,
        json_mode=True,
        strict_json_schema=False,
        stream_usage=True,
    )
    return [
        ModelProfile(
            name="default_chat",
            provider=settings.MODEL_PROVIDER,
            model=settings.LLM_MODEL_NAME,
            temperature=0.2,
            timeout_seconds=settings.MODEL_REQUEST_TIMEOUT_SECONDS,
            capabilities=capabilities,
            extra_body={"enable_thinking": False},
        ),
        ModelProfile(
            name="default_reasoning",
            provider=settings.MODEL_PROVIDER,
            model=settings.LLM_MODEL_NAME,
            temperature=0.1,
            timeout_seconds=settings.MODEL_REQUEST_TIMEOUT_SECONDS,
            capabilities=capabilities,
            extra_body={"enable_thinking": True},
        ),
    ]


def build_model_gateway() -> ModelGateway:
    provider = DashScopeOpenAIProvider(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.MODEL_BASE_URL,
    )
    return ModelGateway(
        providers={settings.MODEL_PROVIDER: provider},
        profiles=default_model_profiles(),
    )


@lru_cache(maxsize=1)
def get_model_gateway() -> ModelGateway:
    return build_model_gateway()
