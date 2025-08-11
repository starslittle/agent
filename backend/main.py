import os
from pathlib import Path
from typing import Dict

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent_factory import create_agent_from_config


ROOT = Path(__file__).resolve().parent
YAML_PATH = ROOT / "agents.yaml"

app = FastAPI(title="Config-driven LangChain Agent Service", version="0.1.0")

# CORS: 允许所有源，便于前端调试
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


class QueryResponse(BaseModel):
    agent_name: str
    # 为了兼容前端，提供 answer 字段；同时保留 output 以兼容潜在旧前端
    answer: str
    output: str | None = None


AGENT_REGISTRY: Dict[str, object] = {}
DEFAULT_AGENT_NAME: str | None = None


@app.on_event("startup")
def load_agents():
    global AGENT_REGISTRY, DEFAULT_AGENT_NAME
    if not YAML_PATH.exists():
        raise RuntimeError(f"agents.yaml not found at {YAML_PATH}")
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    AGENT_REGISTRY = {}
    DEFAULT_AGENT_NAME = None
    for agent_cfg in cfg.get("agents", []):
        name = agent_cfg.get("name")
        conf = agent_cfg.get("config", {})
        if not name:
            continue
        executor = create_agent_from_config(conf)
        AGENT_REGISTRY[name] = executor
        if agent_cfg.get("is_default"):
            DEFAULT_AGENT_NAME = name
    if not DEFAULT_AGENT_NAME and AGENT_REGISTRY:
        DEFAULT_AGENT_NAME = list(AGENT_REGISTRY.keys())[0]


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    agent_name = req.agent_name or DEFAULT_AGENT_NAME
    if not agent_name or agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未找到指定 agent: {agent_name}")
    executor = AGENT_REGISTRY[agent_name]
    # AgentExecutor.invoke 接口
    result = executor.invoke({"input": req.query})
    output = result.get("output") if isinstance(result, dict) else str(result)
    return QueryResponse(agent_name=agent_name, answer=output, output=output)


@app.get("/")
def serve_index():
    # index.html 位于项目根目录
    index_path = (ROOT.parent / "index.html").resolve()
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html 未找到")
    return FileResponse(index_path)


if __name__ == "__main__":
    # 使用模块路径，确保从仓库根目录运行也能正确导入
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)


