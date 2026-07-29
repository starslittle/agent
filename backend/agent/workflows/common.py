from __future__ import annotations

from typing import Any

from agent.events import emit_runtime_event
from agent.models import (
    ModelGateway,
    ModelMessage,
    ModelRequest,
    ModelStreamEventType,
)
from agent.prompts import load_prompt, prompt_version_entry
from agent.state import RootState


def conversation_messages(state: RootState) -> list[ModelMessage]:
    messages = []
    for item in state.get("messages", []):
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append(ModelMessage(role=role, content=content))
    return messages


def prompt_metadata(
    state: RootState,
    *,
    stage: str,
    prompt_path: str,
) -> tuple[str, dict[str, Any]]:
    system_prompt = load_prompt(prompt_path)
    entry = prompt_version_entry(
        stage=stage,
        relative_path=prompt_path,
        rendered_prompt=system_prompt,
    )
    metadata = dict(state.get("metadata") or {})
    metadata["prompt_versions"] = [
        *metadata.get("prompt_versions", []),
        entry,
    ]
    emit_runtime_event("prompt.used", **entry)
    return system_prompt, metadata


def require_model_budget(state: RootState) -> int:
    used = state.get("model_calls", 0)
    if used >= state["max_model_calls"]:
        raise RuntimeError("model call budget exhausted")
    return used + 1


async def stream_model_answer(
    *,
    gateway: ModelGateway,
    state: RootState,
    profile_name: str,
    stage: str,
    prompt_path: str,
    context: str = "",
) -> dict[str, Any]:
    model_calls = require_model_budget(state)
    system_prompt, metadata = prompt_metadata(
        state,
        stage=stage,
        prompt_path=prompt_path,
    )
    user_content = state["query"]
    if context:
        user_content = (
            f"用户问题：{state['query']}\n\n"
            f"可验证的参考信息：\n{context}"
        )
    request = ModelRequest(
        messages=[
            ModelMessage(role="system", content=system_prompt),
            *conversation_messages(state),
            ModelMessage(role="user", content=user_content),
        ]
    )
    answer_parts: list[str] = []
    usage: dict[str, int] = {}
    model_name = ""
    async for event in gateway.stream(
        profile_name,
        request,
        stage=stage,
    ):
        model_name = event.model or model_name
        if event.type == ModelStreamEventType.DELTA and event.text:
            answer_parts.append(event.text)
            emit_runtime_event("answer.delta", text=event.text, stage=stage)
        elif event.type == ModelStreamEventType.USAGE and event.usage:
            usage = event.usage.model_dump()
        elif event.type == ModelStreamEventType.COMPLETED:
            if event.usage is not None:
                usage = event.usage.model_dump()
    answer = "".join(answer_parts)
    return {
        "answer": answer,
        "model_calls": model_calls,
        "usage": usage,
        "metadata": metadata,
    }
