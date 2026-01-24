"""Graph API 路由 - 统一流式输出接口"""

from typing import Dict, Any
from pathlib import Path

import yaml
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.intent_router import classify_and_route
from app.api.agent_factory import create_agent_from_config
from graph import run_graph


_STREAM_AGENT_CACHE: dict[str, object] = {}
_STREAM_DEFAULT: str | None = None


def _resolve_agents_yaml() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    repo_root = backend_root.parent
    candidates = [
        backend_root / "configs" / "agents.yaml",
        backend_root / "agents.yaml",
        repo_root / "configs" / "agents.yaml",
        repo_root / "backend" / "configs" / "agents.yaml",
        repo_root / "agents.yaml",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    tried = " | ".join(str(x) for x in candidates)
    raise FileNotFoundError(f"agents.yaml not found; tried: {tried}")


def _load_stream_agents() -> None:
    global _STREAM_AGENT_CACHE, _STREAM_DEFAULT
    if _STREAM_AGENT_CACHE:
        return
    yaml_path = _resolve_agents_yaml()
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    _STREAM_AGENT_CACHE = {}
    _STREAM_DEFAULT = None
    for agent_cfg in data.get("agents", []):
        name = agent_cfg.get("name")
        conf = agent_cfg.get("config", {})
        if not name:
            continue
        _STREAM_AGENT_CACHE[name] = create_agent_from_config(conf, streaming_override=True)
        if agent_cfg.get("is_default"):
            _STREAM_DEFAULT = name
    if _STREAM_DEFAULT is None and _STREAM_AGENT_CACHE:
        _STREAM_DEFAULT = list(_STREAM_AGENT_CACHE.keys())[0]


def _get_stream_executor(agent_name: str | None):
    _load_stream_agents()
    name = agent_name or _STREAM_DEFAULT
    if not name or name not in _STREAM_AGENT_CACHE:
        raise HTTPException(status_code=404, detail=f"未找到指定 agent: {agent_name}")
    return _STREAM_AGENT_CACHE[name]


async def query_stream_graph(req: Any):
    """
    基于LangGraph的流式查询接口

    Args:
        req: 查询请求

    Returns:
        EventSourceResponse: SSE流式响应
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    async def event_generator():
        """SSE事件生成器"""
        try:
            # 转换聊天历史格式
            chat_history = []
            if req.chat_history:
                for msg in req.chat_history:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        chat_history.append(("human", content))
                    elif role == "assistant":
                        chat_history.append(("ai", content))

            print(f"\n[🌊 Stream] 开始流式处理")
            print(f"[🌊 Stream] 查询: {req.query[:50]}...")
            print(f"[🌊 Stream] 模式: {req.agent_name or 'auto'}")
            print(f"[🌊 Stream] 历史记录: {len(chat_history)} 条")

            # 将 agent_name 转换为 mode_hint（用于隐式意图识别）
            mode_hint = None
            if req.agent_name == "research_agent" or req.agent_name == "research":
                mode_hint = "research"
            elif req.agent_name == "fortune_agent" or req.agent_name == "fortune":
                mode_hint = "fortune"

            # 隐式意图识别得到目标 agent
            routing = classify_and_route(req.query, mode_hint)
            agent_name = routing.get("agent_name")
            executor = _get_stream_executor(agent_name)

            # 准备调用参数（chat_history 必须是列表）
            invoke_params = {
                "input": req.query,
                "context": "",
                "chat_history": chat_history,
            }

            accumulated_output = ""
            has_stream = hasattr(executor, "stream") and callable(executor.stream)

            if has_stream:
                for chunk in executor.stream(invoke_params):
                    if isinstance(chunk, dict) and "output" in chunk:
                        current_output = chunk.get("output", "")
                        if current_output and current_output.startswith(accumulated_output):
                            delta = current_output[len(accumulated_output):]
                            if delta:
                                import json
                                yield {
                                    "event": "message",
                                    "data": json.dumps({
                                        "type": "delta",
                                        "data": delta
                                    }, ensure_ascii=False)
                                }
                                accumulated_output = current_output
            else:
                # 若无 stream 能力，回退为一次性输出
                result = executor.invoke(invoke_params)
                output = result.get("output", "") if isinstance(result, dict) else str(result)
                if output:
                    import json
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "delta",
                            "data": output
                        }, ensure_ascii=False)
                    }

            # 发送完成信号
            import json

            yield {
                "event": "message",
                "data": json.dumps({"type": "done"}, ensure_ascii=False)
            }

            print(f"[✅ Stream] 流式处理完成")

        except Exception as e:
            print(f"[❌ Stream] 错误: {e}")
            import traceback
            traceback.print_exc()

            # 发送错误事件
            import json

            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "message": f"处理失败: {str(e)}"
                }, ensure_ascii=False)
            }

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def query_sync_graph(req: Any) -> Dict[str, Any]:
    """
    基于LangGraph的同步查询接口

    Args:
        req: 查询请求

    Returns:
        Dict: 包含答案的字典
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    try:
        # 转换聊天历史格式
        chat_history = []
        if req.chat_history:
            for msg in req.chat_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    chat_history.append(("human", content))
                elif role == "assistant":
                    chat_history.append(("ai", content))

        print(f"\n[🔄 Graph Sync] 开始同步处理")
        print(f"[🔄 Graph Sync] 查询: {req.query[:50]}...")

        # 同步调用Graph
        result = await run_graph(
            query=req.query,
            chat_history=chat_history,
            mode_hint=None,
        )

        answer = result.get("final_answer", "") or result.get("output", "")

        print(f"[✅ Graph Sync] 同步处理完成")

        return {
            "answer": answer,
            "route": result.get("route", ""),
            "metadata": result.get("metadata", {}),
        }

    except Exception as e:
        print(f"[❌ Graph Sync] 错误: {e}")
        import traceback
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
