from contextlib import asynccontextmanager
import asyncio

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app.core.settings import settings
from .api import agent_runs

if settings.AGENT_RUNTIME_STORE == "postgres":
    # psycopg async connections require the selector loop on Windows. This
    # import must happen before Uvicorn creates the application event loop.
    from app.runtime.postgres_store import (
        configure_psycopg_event_loop_policy,
    )

    configure_psycopg_event_loop_policy()

@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime_store = None
    runtime_notifier = None
    if settings.AGENT_RUNTIME_COORDINATION == "redis":
        from app.runtime.coordination import RedisRuntimeNotifier

        runtime_notifier = await RedisRuntimeNotifier.open(
            settings.REDIS_URL,
            channel_prefix=settings.AGENT_RUNTIME_REDIS_CHANNEL_PREFIX,
        )
    if settings.AGENT_RUNTIME_STORE == "postgres":
        from app.runtime.postgres_store import PostgresRuntimeStore

        runtime_store = await PostgresRuntimeStore.open(
            settings.AGENT_RUNTIME_DATABASE_URL
        )
        checkpointer = None
        if settings.AGENT_EXECUTION_ENGINE == "langgraph_v1":
            checkpointer = await runtime_store.build_checkpointer(
                setup=settings.AGENT_RUNTIME_CHECKPOINT_SETUP,
            )
        agent_runs.configure_runtime_store(
            runtime_store,
            checkpointer=checkpointer,
            notifier=runtime_notifier,
        )
    elif runtime_notifier is not None:
        from app.runtime.store import InMemoryRuntimeStore

        agent_runs.configure_runtime_store(
            InMemoryRuntimeStore(),
            notifier=runtime_notifier,
        )
    maintenance_task = asyncio.create_task(
        _runtime_maintenance(),
        name="agent-runtime-maintenance",
    )
    try:
        yield
    finally:
        maintenance_task.cancel()
        await asyncio.gather(maintenance_task, return_exceptions=True)
        await agent_runs.registry.close()
        if runtime_store is not None:
            await runtime_store.close()


async def _runtime_maintenance() -> None:
    interval = max(30, settings.AGENT_RUNTIME_MAINTENANCE_SECONDS)
    while True:
        await asyncio.sleep(interval)
        try:
            await agent_runs.registry.purge_expired()
        except Exception:
            # Readiness exposes persistent failures. Maintenance retries on
            # the next interval without terminating the Agent Service.
            continue


app = FastAPI(
    title="Qidian Python Agent Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(agent_runs.router)


class QueryRequest(BaseModel):
    query: str
    agent_name: str | None = None
    chat_history: list[dict] | None = None


@app.post("/query_stream")
async def query_stream_endpoint(req: QueryRequest, request: Request):
    """
    唯一对外流式接口（SSE + LangGraph）。
    """
    from .api.graph_routes import query_stream_graph
    from .api.internal_auth import verify_internal_request

    body = await request.body()
    if not verify_internal_request(
        request.headers,
        body,
        method=request.method,
        path=request.url.path,
    ):
        raise HTTPException(status_code=401, detail="invalid internal request")

    return await query_stream_graph(req)


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "python-agent-service",
        "service_version": settings.AGENT_SERVICE_VERSION,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=int(settings.PORT or 8000), reload=True
    )
