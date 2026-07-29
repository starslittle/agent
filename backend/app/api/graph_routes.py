"""Thin Legacy SSE adapter over the single Agent Runtime execution path."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

from app.runtime.models import AgentRunRequest, ChatMessage

from . import agent_runs


def _legacy_request(req: Any) -> AgentRunRequest:
    query = str(req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    execution_id = f"legacy-{uuid.uuid4().hex}"
    messages = []
    for item in req.chat_history or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append(ChatMessage(role=role, content=content))
    agent_name = str(req.agent_name or "default_llm_agent")
    return AgentRunRequest(
        execution_id=execution_id,
        run_id=execution_id,
        request_id=uuid.uuid4().hex,
        idempotency_key=execution_id,
        conversation_id="legacy-compatibility",
        agent_name=agent_name,
        query=query,
        messages=messages,
        metadata={"transport": "legacy_sse"},
    )


def _message(payload: dict) -> dict[str, str]:
    return {
        "event": "message",
        "data": json.dumps(payload, ensure_ascii=False),
    }


async def query_stream_graph(req: Any) -> EventSourceResponse:
    """Map stable AgentEvents to the historical browser message envelope."""
    request = _legacy_request(req)
    execution = await agent_runs.registry.start(request)

    async def event_generator():
        thinking_step = 0
        answer_started = False
        async for event in agent_runs.registry.events(execution):
            if event.type == "progress":
                thinking_step += 1
                message = str(
                    event.data.get("message")
                    or event.data.get("stage")
                    or "处理中"
                )
                yield _message(
                    {
                        "type": "delta",
                        "data": f"Step{thinking_step}: {message}\n",
                        "isThinking": True,
                        "thinkingFinished": False,
                    }
                )
            elif event.type == "answer.delta":
                text = str(event.data.get("text") or "")
                if not text:
                    continue
                yield _message(
                    {
                        "type": "delta",
                        "data": text,
                        "isThinking": False,
                        "thinkingFinished": not answer_started,
                    }
                )
                answer_started = True
            elif event.type in {
                "run.failed",
                "run.cancelled",
                "run.timed_out",
            }:
                yield _message(
                    {
                        "type": "error",
                        "message": str(
                            event.data.get("message")
                            or event.data.get("code")
                            or "Agent 运行失败"
                        ),
                    }
                )
                return
            elif event.type == "run.completed":
                yield _message({"type": "done"})
                return

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
