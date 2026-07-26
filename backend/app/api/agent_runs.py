from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.api.internal_auth import verify_internal_request
from app.core.settings import settings
from app.runtime import AgentRunRequest, ExecutionRegistry, GraphAgentRuntime
from app.runtime.registry import (
    ExecutionNotFoundError,
    IdempotencyConflictError,
)


router = APIRouter()
registry = ExecutionRegistry(
    GraphAgentRuntime(),
    service_version=settings.AGENT_SERVICE_VERSION,
    retention_seconds=settings.AGENT_RUNTIME_RETENTION_SECONDS,
)


def _verify(request: Request, body: bytes, execution_id: str) -> None:
    if not verify_internal_request(
        request.headers,
        body,
        method=request.method,
        path=request.url.path,
        execution_id=execution_id,
    ):
        raise HTTPException(status_code=401, detail="invalid internal request")


@router.get("/internal/health")
async def internal_health():
    return {
        "status": "ok",
        "service": "python-agent-service",
        "service_version": settings.AGENT_SERVICE_VERSION,
        "protocol_versions": [1],
        "runtime_registry": "single-replica-memory",
    }


@router.get("/internal/v1/capabilities")
async def capabilities():
    from agent.tools.registry import get_tool_registry

    return {
        "protocol_version": 1,
        "service_version": settings.AGENT_SERVICE_VERSION,
        "agents": ["default_llm_agent", "research_agent", "fortune_agent"],
        "tools": get_tool_registry().capabilities(),
        "runtime_registry": "single-replica-memory",
    }


@router.post("/internal/v1/agent-runs:stream")
async def stream_agent_run(
    request: Request,
    starting_after: int = Query(default=0, ge=0),
):
    body = await request.body()
    if len(body) > settings.AGENT_MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="request too large")
    try:
        run_request = AgentRunRequest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    _verify(request, body, run_request.execution_id)
    try:
        execution = await registry.start(run_request)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail="idempotency conflict") from exc

    async def generate():
        async for event in registry.events(
            execution,
            starting_after=starting_after,
        ):
            yield {
                "event": event.type,
                "id": event.sse_id,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(
        generate(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Agent-Protocol-Version": "1",
        },
    )


@router.get("/internal/v1/agent-runs/{execution_id}")
async def get_agent_run(execution_id: str, request: Request):
    _verify(request, b"", execution_id)
    try:
        snapshot = await registry.snapshot(execution_id)
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="execution not found") from exc
    return snapshot


@router.delete("/internal/v1/agent-runs/{execution_id}")
async def cancel_agent_run(execution_id: str, request: Request):
    _verify(request, b"", execution_id)
    try:
        before = await registry.snapshot(execution_id)
        snapshot = await registry.cancel(execution_id)
    except ExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="execution not found") from exc
    status_code = 200 if before.status.terminal else 202
    return JSONResponse(
        status_code=status_code,
        content=json.loads(snapshot.model_dump_json()),
    )
