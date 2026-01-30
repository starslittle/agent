import os
import json
from pathlib import Path
from typing import Dict, AsyncGenerator

import uvicorn
from dotenv import load_dotenv
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 先加载.env文件，再导入settings
APP_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = APP_DIR.parent
REPO_ROOT = APP_DIR.parents[1]

# 加载.env文件
try:
    if (BACKEND_ROOT / ".env").exists():
        load_dotenv(BACKEND_ROOT / ".env")
        print(f"[ENV] Loaded .env from {BACKEND_ROOT / '.env'}")
    else:
        load_dotenv(REPO_ROOT / ".env")
        print(f"[ENV] Loaded .env from {REPO_ROOT / '.env'}")
except Exception as _e:
    print(f"[ENV] Failed to load .env: {_e}")

# 现在可以安全导入settings
from app.core.settings import settings

from .api.agent_factory import create_agent_from_config
from sse_starlette.sse import EventSourceResponse

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


try:
    if (BACKEND_ROOT / ".env").exists():
        load_dotenv(BACKEND_ROOT / ".env")
    else:
        load_dotenv(REPO_ROOT / ".env")
    if settings.DASHSCOPE_API_KEY:
        print("[ENV] DASHSCOPE_API_KEY loaded from .env or environment")
    else:
        print("[ENV] DASHSCOPE_API_KEY is missing; streaming LLM calls may fail")
except Exception as _e:
    print(f"[ENV] Failed to load .env: {_e}")


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
        executor = create_agent_from_config(conf, streaming_override=False)
        AGENT_REGISTRY[name] = executor
        AGENT_REGISTRY[name + "_stream"] = create_agent_from_config(conf, streaming_override=True)
        if agent_cfg.get("is_default"):
            DEFAULT_AGENT_NAME = name
    if not DEFAULT_AGENT_NAME and AGENT_REGISTRY:
        DEFAULT_AGENT_NAME = list(AGENT_REGISTRY.keys())[0]
    _AGENTS_INITIALIZED = True

    # 初始化 Redis（可选）
    try:
        from redis import asyncio as aioredis  # type: ignore
        if settings.REDIS_URL:
            app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            print(f"[REDIS] connected: {settings.REDIS_URL}")
        else:
            app.state.redis = None
            print("[REDIS] disabled (REDIS_URL not set)")
    except Exception as _re:
        app.state.redis = None
        print(f"[REDIS] init failed: {_re}")


@app.post("/query_stream_sse")
async def query_stream_sse(req: QueryRequest):
    """流式问答接口，使用 SSE 协议"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    # ========== 智能体选择逻辑（流式） ==========
    # 当前配置：仅使用通用智能体
    agent_name = "default_llm_agent"

    # 确保agent存在
    if not agent_name or agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未找到指定 agent: {agent_name}")

    async def event_generator():
        """
        这是SSE的核心：异步生成器
        每次yield一个字典，sse-starlette会自动转换成SSE格式
        """
        try:
            executor = AGENT_REGISTRY.get(agent_name)
            if not executor:
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "error", "message": f"Agent {agent_name} 不存在"}, ensure_ascii=False)
                }
                return

            # 准备调用参数（chat_history 必须是列表，不能是None）
            history = []
            if req.chat_history:
                for msg in req.chat_history:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        history.append(("human", content))
                    elif role == "assistant":
                        history.append(("ai", content))

            invoke_params = {
                "input": req.query,
                "context": "",
                "chat_history": history  # 始终提供列表，即使为空
            }

            accumulated_output = ""

            has_stream = hasattr(executor, "stream") and callable(executor.stream)

            if has_stream:
                # Agent 支持流式输出
                print(f"🌊 [后端] 开始流式处理")
                chunk_count = 0
                delta_count = 0

                for chunk in executor.stream(invoke_params):
                    chunk_count += 1
                    if isinstance(chunk, dict) and "output" in chunk:
                        current_output = chunk.get("output", "")

                        if current_output and current_output.startswith(accumulated_output):
                            delta = current_output[len(accumulated_output):]
                            if delta:
                                delta_count += 1
                                # 发送增量数据
                                yield {
                                    "event": "message",
                                    "data": json.dumps({
                                        "type": "delta",
                                        "data": delta
                                    }, ensure_ascii=False)
                                }
                            accumulated_output = current_output

                # 流式完成，发送done信号
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "done"}, ensure_ascii=False)
                }

            else:
                # ===== 场景B：Agent不支持流式输出 =====
                # 调用executor.invoke()方法，同步获取结果
                result = executor.invoke(invoke_params)

                # 提取输出内容
                if isinstance(result, dict):
                    output = result.get("output", "")
                else:
                    output = str(result)

                # 一次性发送完整输出
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": "delta",
                        "data": output  # 完整内容
                    }, ensure_ascii=False)
                }

                # 发送完成信号
                yield {
                    "event": "message",
                    "data": json.dumps({"type": "done"}, ensure_ascii=False)
                }

        except Exception as e:
            # 错误处理
            print(f"SSE流式处理异常: {e}")
            import traceback
            traceback.print_exc()

            # 向前端发送错误事件
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "message": f"处理失败: {str(e)}"
                }, ensure_ascii=False)
            }

    print(f"📡 [后端] 返回EventSourceResponse")
    # 返回SSE响应
    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ===== 新的基于LangGraph的API端点 =====

@app.post("/query_stream_graph")
async def query_stream_graph_endpoint(req: QueryRequest):
    """
    基于LangGraph的流式查询接口（新版本）

    支持三种模式：
    - default: 常规对话
    - research: 深度思考（工具+RAG）
    - fortune: 命理分析
    """
    from .api.graph_routes import query_stream_graph
    return await query_stream_graph(req)


@app.post("/query_sync_graph")
async def query_sync_graph_endpoint(req: QueryRequest):
    """
    基于LangGraph的同步查询接口（新版本）

    返回完整答案而不是流式
    """
    from .api.graph_routes import query_sync_graph
    return await query_sync_graph(req)


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
    raise HTTPException(status_code=404, detail="前端页面未找到：请先在 frontend 目录执行构建")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(settings.PORT or 8002), reload=True)
