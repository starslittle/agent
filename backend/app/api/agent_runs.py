from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.api.internal_auth import verify_internal_request
from app.core.settings import settings
from app.runtime import (
    AgentRouteRequest,
    AgentRunRequest,
    ExecutionRegistry,
    build_agent_runtime,
)
from app.runtime.store import InMemoryRuntimeStore, RuntimeStore
from app.runtime.registry import (
    ExecutionNotFoundError,
    IdempotencyConflictError,
)
from agent.models import UnknownModelIDError
from agent.skills import (
    ConflictingSkillRequestError,
    UnknownRequestedSkillError,
    get_skill_registry,
    public_skill_catalog,
)


router = APIRouter()


def build_execution_registry(
    store: RuntimeStore | None = None,
    *,
    checkpointer=None,
    notifier=None,
) -> ExecutionRegistry:
    runtime_store = store or InMemoryRuntimeStore()
    return ExecutionRegistry(
        build_agent_runtime(
            checkpointer=checkpointer,
            lease_guard=runtime_store,
            artifact_stager=runtime_store,
        ),
        service_version=settings.AGENT_SERVICE_VERSION,
        retention_seconds=settings.AGENT_RUNTIME_RETENTION_SECONDS,
        store=runtime_store,
        lease_seconds=settings.AGENT_RUNTIME_LEASE_SECONDS,
        event_poll_seconds=settings.AGENT_RUNTIME_EVENT_POLL_SECONDS,
        notifier=notifier,
    )


registry = build_execution_registry()


def configure_runtime_store(
    store: RuntimeStore,
    *,
    checkpointer=None,
    notifier=None,
) -> None:
    global registry
    registry = build_execution_registry(
        store,
        checkpointer=checkpointer,
        notifier=notifier,
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
        "runtime_store": registry.store_kind,
        "execution_engine": settings.AGENT_EXECUTION_ENGINE,
    }


@router.get("/internal/ready")
async def internal_ready():
    from agent.readiness import validate_target_runtime

    try:
        report = validate_target_runtime()
        runtime_store = await registry.validate_store()
        if (
            settings.AGENT_EXECUTION_ENGINE == "langgraph_v1"
            and settings.AGENT_RUNTIME_STORE == "postgres"
            and not runtime_store.get("checkpoint_ready")
        ):
            raise ValueError("PostgreSQL checkpoint schema is not ready")
        if (
            settings.AGENT_EXECUTION_ENGINE == "langgraph_v1"
            and not settings.DASHSCOPE_API_KEY
        ):
            raise ValueError("DASHSCOPE_API_KEY is required")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "code": type(exc).__name__,
            },
        ) from exc
    return {
        "status": "ready",
        "execution_engine": settings.AGENT_EXECUTION_ENGINE,
        "runtime_store": runtime_store,
        **report,
    }


@router.get("/internal/v1/capabilities")
async def capabilities():
    from agent.capabilities import target_capability_schemas
    from agent.specs import get_agent_catalog
    from agent.tools.registry import get_tool_registry

    return {
        "protocol_version": 1,
        "service_version": settings.AGENT_SERVICE_VERSION,
        "agents": get_agent_catalog().names(),
        "tools": get_tool_registry().capabilities(),
        "target_capabilities": target_capability_schemas(),
        "runtime_store": registry.store_kind,
        "execution_engine": settings.AGENT_EXECUTION_ENGINE,
    }


@router.get("/internal/v1/skills")
async def skills(request: Request):
    _verify(request, b"", "skill-catalog")
    effective_skill_ids: set[str] = set()
    try:
        from agent.readiness import validate_target_runtime

        validate_target_runtime()
        if settings.DASHSCOPE_API_KEY:
            effective_skill_ids.add("fortune")
            if settings.TAVILY_API_KEY:
                effective_skill_ids.add("research")
    except Exception:
        # The caller only receives an understandable effective flag. Internal
        # readiness reasons stay on the service side.
        effective_skill_ids.clear()
    return {
        "items": [
            item.model_dump(mode="json")
            for item in public_skill_catalog(
                get_skill_registry(), effective_skill_ids=effective_skill_ids
            )
        ]
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
    except (UnknownModelIDError, UnknownRequestedSkillError) as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    except ConflictingSkillRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
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


@router.post("/internal/v1/agent-routes:resolve")
async def resolve_agent_route(request: Request):
    body = await request.body()
    if len(body) > settings.AGENT_MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="request too large")
    try:
        route_request = AgentRouteRequest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    _verify(request, body, route_request.execution_id)
    try:
        return await registry.resolve_route(route_request)
    except (UnknownModelIDError, UnknownRequestedSkillError) as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    except ConflictingSkillRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc


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
