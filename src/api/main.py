import os
import json
from pathlib import Path
from typing import Dict, AsyncGenerator

import uvicorn
from dotenv import load_dotenv
from src.core.settings import settings
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent_factory import create_agent_from_config
from src.rag.pipelines import query as rag_core_query
from src.rag.pipelines import query_fortune


API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parents[1]

def _resolve_agents_yaml() -> Path:
    candidates = [
        PROJECT_ROOT / "configs" / "agents.yaml",
        PROJECT_ROOT / "backend" / "agents.yaml",
        PROJECT_ROOT / "agents.yaml",
        API_DIR / "agents.yaml",
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
    load_dotenv(PROJECT_ROOT / ".env")
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


class QueryResponse(BaseModel):
    agent_name: str
    answer: str
    output: str | None = None


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


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    agent_name = req.agent_name or DEFAULT_AGENT_NAME
    if not agent_name or agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未找到指定 agent: {agent_name}")
    executor = AGENT_REGISTRY.get(agent_name + "_stream") or AGENT_REGISTRY[agent_name]
    invoke_params = {"input": req.query, "context": ""}
    if req.chat_history:
        history = []
        for msg in req.chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history.append(("human", content))
            elif role == "assistant":
                history.append(("ai", content))
        invoke_params["chat_history"] = history
    try:
        result = executor.invoke(invoke_params)
        raw = result.get("output") if isinstance(result, dict) else str(result)
    except Exception as e:
        err = f"请求失败：{e}"
        # 返回 200，前端可显示错误文本，避免 500 中断
        return QueryResponse(agent_name=agent_name, answer=err, output=err)

    def _post_clean(text: str) -> str:
        lines = [ln.rstrip() for ln in (text or "").splitlines()]
        cleaned: list[str] = []
        for ln in lines:
            low = ln.lstrip().lower()
            if low.startswith("citations:") or low.startswith("notes:"):
                continue
            if low in ("missinginfo: none",):
                continue
            cleaned.append(ln)
        return "\n".join(cleaned).strip()

    output = _post_clean(str(raw))
    return QueryResponse(agent_name=agent_name, answer=output, output=output)


async def stream_agent_response(executor, invoke_params: Dict) -> AsyncGenerator[str, None]:
    try:
        print(f"[DEBUG] 开始流式处理，参数: {invoke_params}")
        api_key = settings.DASHSCOPE_API_KEY or ""
        if not api_key:
            print("[ERROR] DASHSCOPE_API_KEY 未设置，无法进行流式调用")
            yield json.dumps({"type": "error", "message": "API Key 未设置，请检查环境变量 DASHSCOPE_API_KEY"}, ensure_ascii=False) + "\n"
            return
        print("[DEBUG] 使用 executor.stream 方法")
        chunk_count = 0
        accumulated_output = ""
        # 本地清洗函数（与非流式一致）
        def _post_clean(text: str) -> str:
            lines = [ln.rstrip() for ln in (text or "").splitlines()]
            cleaned: list[str] = []
            for ln in lines:
                low = ln.lstrip().lower()
                if low.startswith("citations:") or low.startswith("notes:"):
                    continue
                if low in ("missinginfo: none",):
                    continue
                cleaned.append(ln)
            return "\n".join(cleaned).strip()

        try:
            for chunk in executor.stream(invoke_params):
                chunk_count += 1
                print(f"[DEBUG] executor stream chunk #{chunk_count}: {chunk}")
                if isinstance(chunk, dict) and "output" in chunk:
                    current_output = chunk.get("output", "")
                    if current_output and current_output != accumulated_output:
                        if current_output.startswith(accumulated_output):
                            new_content = current_output[len(accumulated_output):]
                            accumulated_output = current_output
                            if new_content:
                                print(f"[DEBUG] 发送增量: {repr(new_content)}")
                                yield json.dumps({"type": "delta", "data": new_content}, ensure_ascii=False) + "\n"
                        else:
                            accumulated_output = current_output
                            print(f"[DEBUG] 发送完整输出: {repr(current_output)}")
                            yield json.dumps({"type": "delta", "data": current_output}, ensure_ascii=False) + "\n"
        except Exception as stream_err:
            # 流式失败兜底：尝试非流式一次
            print(f"[WARNING] 流式过程中出错，回退非流式: {stream_err}")
            # 二级兜底：直接使用 DashScope 原生 SDK 进行简化流式生成（不走 Agent，确保可流式）
            try:
                from dashscope import Generation  # type: ignore
                import dashscope as _dashscope  # type: ignore
                from http import HTTPStatus

                _dashscope.api_key = settings.DASHSCOPE_API_KEY or ""
                system_prompt = (
                    "你是中文助手。尽量简洁、直接回答用户问题；如果提供了背景上下文，可结合其回答。"
                )
                user_prompt = (invoke_params.get("input") or "").strip()
                context_text = (invoke_params.get("context") or "").strip()
                if context_text:
                    user_prompt = f"{user_prompt}\n\n[背景]\n{context_text}"

                responses = Generation.call(
                    model="qwen-turbo-2025-07-15",
                    input={
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ]
                    },
                    stream=True,
                    incremental_output=True,
                )
                for resp in responses:
                    try:
                        if resp.status_code == HTTPStatus.OK:
                            # 优先使用简化文本，否则走消息结构
                            content = getattr(resp, "output_text", "") or (
                                (((resp.output or {}).get("choices") or [{}])[0])
                                .get("message", {})
                                .get("content", "")
                            )
                            if content:
                                yield json.dumps({"type": "delta", "data": content}, ensure_ascii=False) + "\n"
                        else:
                            # 错误事件：输出 message 以便前端可见
                            msg = getattr(resp, "message", str(resp))
                            yield json.dumps({"type": "delta", "data": f"[LLM错误] {msg}"}, ensure_ascii=False) + "\n"
                    except Exception:
                        continue
                yield json.dumps({"type": "done"}) + "\n"
                return
            except Exception as _sdk_err:
                print(f"[WARNING] DashScope 原生流式兜底失败: {_sdk_err}")
            try:
                result = executor.invoke(invoke_params)
                output = result.get("output") if isinstance(result, dict) else str(result)
                cleaned_output = _post_clean(output)
                if cleaned_output:
                    yield json.dumps({"type": "delta", "data": cleaned_output}, ensure_ascii=False) + "\n"
                    yield json.dumps({"type": "done"}) + "\n"
                    return
            except Exception as fallback_err:
                print(f"[ERROR] 非流式兜底也失败: {fallback_err}")
                yield json.dumps({"type": "error", "message": f"处理失败: {str(fallback_err)}"}, ensure_ascii=False) + "\n"
                return
        print(f"[DEBUG] executor stream 完成，总chunk数: {chunk_count}")
        if not accumulated_output:
            print("[WARNING] executor.stream 没有产生输出，回退到非流式调用")
            try:
                result = executor.invoke(invoke_params)
                output = result.get("output") if isinstance(result, dict) else str(result)
                if output:
                    cleaned_output = _post_clean(output)  # type: ignore[name-defined]
                    if cleaned_output:
                        yield json.dumps({"type": "delta", "data": cleaned_output}, ensure_ascii=False) + "\n"
            except Exception as fallback_error:
                print(f"[ERROR] 非流式回退也失败: {fallback_error}")
                yield json.dumps({"type": "error", "message": f"处理失败: {str(fallback_error)}"}, ensure_ascii=False) + "\n"
                return
        yield json.dumps({"type": "done"}) + "\n"
    except Exception as e:
        print(f"[ERROR] 流式处理异常: {e}")
        import traceback
        traceback.print_exc()
        # 失败兜底：再尝试一次非流式
        try:
            result = executor.invoke(invoke_params)
            output = result.get("output") if isinstance(result, dict) else str(result)
            def _post_clean2(text: str) -> str:
                lines = [ln.rstrip() for ln in (text or "").splitlines()]
                cleaned: list[str] = []
                for ln in lines:
                    low = ln.lstrip().lower()
                    if low.startswith("citations:") or low.startswith("notes:"):
                        continue
                    if low in ("missinginfo: none",):
                        continue
                    cleaned.append(ln)
                return "\n".join(cleaned).strip()
            cleaned_output = _post_clean2(output)
            if cleaned_output:
                yield json.dumps({"type": "delta", "data": cleaned_output}, ensure_ascii=False) + "\n"
                yield json.dumps({"type": "done"}) + "\n"
                return
        except Exception as e2:
            error_msg = str(e)
            if "KeyError: 'request'" in error_msg or "HTTPError" in error_msg:
                yield json.dumps({"type": "error", "message": "API 调用失败，请检查 DASHSCOPE_API_KEY 是否正确设置并且有效"}, ensure_ascii=False) + "\n"
            else:
                yield json.dumps({"type": "error", "message": f"处理异常: {error_msg}"}, ensure_ascii=False) + "\n"


@app.post("/query_stream")
async def query_stream(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    agent_name = req.agent_name or DEFAULT_AGENT_NAME
    if not agent_name or agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=404, detail=f"未找到指定 agent: {agent_name}")
    executor = AGENT_REGISTRY[agent_name]
    invoke_params = {"input": req.query, "context": ""}
    if req.chat_history:
        history = []
        for msg in req.chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history.append(("human", content))
            elif role == "assistant":
                history.append(("ai", content))
        invoke_params["chat_history"] = history
    return StreamingResponse(
        stream_agent_response(executor, invoke_params),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/v1/query", response_model=QueryResponse)
def query_v1(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    try:
        if (req.agent_name or "") == "fortune_agent":
            answer = query_fortune(req.query)
        else:
            answer = rag_core_query(req.query, agent_name=req.agent_name)
    except Exception as e:
        # 降级为直接返回错误文本，避免 500
        err_text = f"RAG 查询失败: {e}"
        return QueryResponse(agent_name=req.agent_name or (DEFAULT_AGENT_NAME or ""), answer=err_text, output=err_text)

    def _post_clean(text: str) -> str:
        lines = [ln.rstrip() for ln in (text or "").splitlines()]
        cleaned: list[str] = []
        for ln in lines:
            low = ln.lstrip().lower()
            if low.startswith("citations:") or low.startswith("notes:"):
                continue
            if low in ("missinginfo: none",):
                continue
            cleaned.append(ln)
        return "\n".join(cleaned).strip()

    cleaned = _post_clean(str(answer))
    return QueryResponse(agent_name=req.agent_name or (DEFAULT_AGENT_NAME or ""), answer=cleaned, output=cleaned)


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "agents": list(AGENT_REGISTRY.keys()),
        "default_agent": DEFAULT_AGENT_NAME,
    }


@app.get("/")
def serve_index():
    dist_index = (PROJECT_ROOT / "frontend" / "dist" / "index.html").resolve()
    if dist_index.exists():
        return FileResponse(dist_index)
    index_path = (PROJECT_ROOT / "index.html").resolve()
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="前端页面未找到：请先在 frontend 目录执行构建")


DIST_DIR = (PROJECT_ROOT / "frontend" / "dist").resolve()
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=int(settings.PORT or 8000), reload=True)


