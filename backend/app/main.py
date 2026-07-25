from pathlib import Path
from typing import Dict

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

APP_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = APP_DIR.parent
REPO_ROOT = APP_DIR.parents[1]

from app.core.settings import settings

from .api.agent_factory import create_agent_from_config

if settings.DASHSCOPE_API_KEY:
    print("[ENV] DASHSCOPE_API_KEY loaded successfully")
else:
    print("[ENV] WARNING: DASHSCOPE_API_KEY is missing; streaming LLM calls may fail")


def _resolve_agents_yaml() -> Path:
    candidates = [
        BACKEND_ROOT / "configs" / "agents.yaml",
        BACKEND_ROOT / "agents.yaml",
        REPO_ROOT / "configs" / "agents.yaml",
        REPO_ROOT / "backend" / "configs" / "agents.yaml",
        REPO_ROOT / "agents.yaml",
        APP_DIR / "agents.yaml",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    tried = " | ".join(str(x) for x in candidates)
    raise RuntimeError(f"agents.yaml not found; tried: {tried}")


app = FastAPI(title="Config-driven LangChain Agent Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    agent_name: str | None = None
    chat_history: list[dict] | None = None


AGENT_REGISTRY: Dict[str, object] = {}
DEFAULT_AGENT_NAME: str | None = None
_AGENTS_INITIALIZED: bool = False  # 防止在 --reload 下重复初始化


@app.on_event("startup")
def load_agents():
    global AGENT_REGISTRY, DEFAULT_AGENT_NAME, _AGENTS_INITIALIZED
    if _AGENTS_INITIALIZED:
        return
    yaml_path = _resolve_agents_yaml()
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    AGENT_REGISTRY.clear()
    DEFAULT_AGENT_NAME = None
    for agent_cfg in cfg.get("agents", []):
        name = agent_cfg.get("name")
        conf = agent_cfg.get("config", {})
        if not name:
            continue
        # 为流式接口准备一个启用 streaming 的执行器缓存（键: name+'_stream'）
        executor = create_agent_from_config(
            conf, streaming_override=False, agent_name=name
        )
        AGENT_REGISTRY[name] = executor
        AGENT_REGISTRY[name + "_stream"] = create_agent_from_config(
            conf,
            streaming_override=True,
            agent_name=name,
        )
        if agent_cfg.get("is_default"):
            DEFAULT_AGENT_NAME = name
    if not DEFAULT_AGENT_NAME and AGENT_REGISTRY:
        DEFAULT_AGENT_NAME = list(AGENT_REGISTRY.keys())[0]
    _AGENTS_INITIALIZED = True

    # 初始化 Redis（可选）
    try:
        from redis import asyncio as aioredis  # type: ignore

        if settings.REDIS_URL:
            app.state.redis = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True
            )
            print(f"[REDIS] connected: {settings.REDIS_URL}")
        else:
            app.state.redis = None
            print("[REDIS] disabled (REDIS_URL not set)")
    except Exception as _re:
        app.state.redis = None
        print(f"[REDIS] init failed: {_re}")


@app.post("/query_stream")
async def query_stream_endpoint(req: QueryRequest, request: Request):
    """
    唯一对外流式接口（SSE + LangGraph）。
    """
    from .api.graph_routes import query_stream_graph
    from .api.internal_auth import verify_internal_request

    body = await request.body()
    if not verify_internal_request(request.headers, body):
        raise HTTPException(status_code=401, detail="invalid internal request")

    return await query_stream_graph(req)


# ===== 原有的API端点（保留兼容） =====


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "agents": list(AGENT_REGISTRY.keys()),
        "default_agent": DEFAULT_AGENT_NAME,
        "graph_enabled": True,  # 标识Graph功能已启用
        "graph_modes": ["default", "research", "fortune"],
    }


DIST_DIR = (REPO_ROOT / "frontend" / "dist").resolve()
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")


@app.get("/")
def serve_index():
    dist_index = (REPO_ROOT / "frontend" / "dist" / "index.html").resolve()
    if dist_index.exists():
        return FileResponse(dist_index)
    index_path = (REPO_ROOT / "index.html").resolve()
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(
        status_code=404, detail="前端页面未找到：请先在 frontend 目录执行构建"
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=int(settings.PORT or 8000), reload=True
    )
