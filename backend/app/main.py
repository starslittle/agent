import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from app.core.settings import settings
from .api.agent_runs import router as agent_runs_router

if settings.DASHSCOPE_API_KEY:
    print("[ENV] DASHSCOPE_API_KEY loaded successfully")
else:
    print("[ENV] WARNING: DASHSCOPE_API_KEY is missing; streaming LLM calls may fail")


app = FastAPI(title="Qidian Python Agent Service", version="1.0.0")
app.include_router(agent_runs_router)


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


# ===== 原有的API端点（保留兼容） =====


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "python-agent-service",
        "service_version": settings.AGENT_SERVICE_VERSION,
        "protocol_versions": [1],
        "graph_enabled": True,  # 标识Graph功能已启用
        "graph_modes": ["default", "research", "fortune"],
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=int(settings.PORT or 8000), reload=True
    )
