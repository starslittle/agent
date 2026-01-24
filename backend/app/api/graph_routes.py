"""Graph API 路由 - 统一流式输出接口"""

from typing import Dict, Any
from pathlib import Path

import yaml
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.intent_router import classify_and_route
from app.api.agent_factory import create_agent_from_config
from app.core.settings import settings
from rag.pipelines import query_fortune
from langchain_community.chat_models import ChatTongyi
from langchain_tavily import TavilySearch
from graph import run_graph, stream_graph


_STREAM_AGENT_CACHE: dict[str, object] = {}
_STREAM_DEFAULT: str | None = None
_FORTUNE_RAG_ENABLED = False  # 临时暂停命理RAG


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
        _STREAM_AGENT_CACHE[name] = create_agent_from_config(
            conf,
            streaming_override=True,
            agent_name=name,
        )
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


def _grade_context(question: str, context: str) -> bool:
    """判断内部检索内容是否足够回答问题。"""
    prompt = (
        "你是检索质量评估器。判断给定【检索内容】是否足以回答【用户问题】。\n"
        "只回答 YES 或 NO，不要输出其他内容。\n\n"
        f"用户问题：{question}\n\n"
        f"检索内容：{context}\n"
    )
    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "qwen-plus-2025-07-28",
        temperature=0.0,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )
    try:
        res = llm.invoke(prompt)
        text = getattr(res, "content", str(res)).strip().upper()
        return text.startswith("YES")
    except Exception:
        # 保守策略：失败时认为不足，触发外部检索
        return False


def _web_search(query: str, max_results: int = 5) -> str:
    """使用 Tavily 进行网络搜索并格式化结果。"""
    t = TavilySearch(max_results=max_results)
    try:
        results = t.invoke({"query": query})  # type: ignore
    except Exception:
        results = []
    try:
        if isinstance(results, dict) and "results" in results:
            items = results.get("results") or []
        else:
            items = results or []
    except Exception:
        items = []
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title") or ""
            content = item.get("content") or item.get("snippet") or ""
            url = item.get("url") or item.get("link") or ""
        else:
            s = str(item)
            title = s[:60]
            content = s
            url = ""
        lines.append(f"- 标题: {title}\n  摘要: {content}\n  链接: {url}")
    return "\n".join(lines).strip()


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

            accumulated_output = ""
            last_plan_completed = 0
            seen_plan_current = None
            sent_plan_list = False
            thinking_finished_sent = False
            async for chunk in stream_graph(
                query=req.query,
                chat_history=chat_history,
                mode_hint=mode_hint,
            ):
                current_output = ""
                if isinstance(chunk, dict):
                    # 计划/执行过程提示（不包含思维链）
                    plan_tasks = chunk.get("plan_tasks") or []
                    plan_completed = chunk.get("plan_completed") or []
                    plan_current = chunk.get("plan_current")

                    if plan_tasks and not sent_plan_list:
                        sent_plan_list = True
                        plan_text = "【计划】" + "；".join(plan_tasks[:6])
                        import json
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "delta",
                                "data": plan_text + "\n",
                                "isThinking": True,
                                "thinkingFinished": False,
                            }, ensure_ascii=False)
                        }

                    if plan_current and plan_current != seen_plan_current:
                        seen_plan_current = plan_current
                        import json
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "delta",
                                "data": f"【步骤】开始：{plan_current}\n",
                                "isThinking": True,
                                "thinkingFinished": False,
                            }, ensure_ascii=False)
                        }

                    if len(plan_completed) > last_plan_completed:
                        newly = plan_completed[last_plan_completed:]
                        last_plan_completed = len(plan_completed)
                        for item in newly:
                            import json
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "type": "delta",
                                    "data": f"【步骤】完成：{item}\n",
                                    "isThinking": True,
                                    "thinkingFinished": False,
                                }, ensure_ascii=False)
                            }

                    current_output = chunk.get("final_answer") or chunk.get("output", "")
                else:
                    current_output = str(chunk)
                if current_output and current_output.startswith(accumulated_output):
                    delta = current_output[len(accumulated_output):]
                    if delta:
                        import json
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "delta",
                                "data": delta,
                                "isThinking": False,
                                "thinkingFinished": not thinking_finished_sent,
                            }, ensure_ascii=False)
                        }
                        thinking_finished_sent = True
                        accumulated_output = current_output

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
