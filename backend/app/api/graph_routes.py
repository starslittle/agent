"""Graph API 路由 - 统一流式输出接口"""

from typing import Dict, Any
import sys
import time
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


def _safe_preview(text: str, limit: int = 50) -> str:
    s = (text or "")[:limit]
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return s.encode(encoding, errors="replace").decode(encoding, errors="replace")


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
        model=settings.LLM_MODEL_NAME or "deepseek-v4-flash",
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
            stream_started_at = time.perf_counter()
            first_delta_sent_at: float | None = None
            delta_count = 0
            thinking_delta_count = 0
            answer_delta_count = 0
            final_output_len = 0

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

            print("\n[Stream] 开始流式处理")
            print(f"[Stream] 查询: {_safe_preview(req.query)}...")
            print(f"[Stream] 模式: {req.agent_name or 'auto'}")
            print(f"[Stream] 历史记录: {len(chat_history)} 条")

            # 将 agent_name 转换为 mode_hint（用于隐式意图识别）
            mode_hint = None
            if req.agent_name == "research_agent" or req.agent_name == "research":
                mode_hint = "research"
            elif req.agent_name == "fortune_agent" or req.agent_name == "fortune":
                mode_hint = "fortune"

            accumulated_output = ""
            last_plan_completed = 0
            seen_plan_current = None
            emitted_thinking_keys: set[str] = set()
            thinking_step_index = 0
            thinking_finished_sent = False
            async for chunk in stream_graph(
                query=req.query,
                chat_history=chat_history,
                mode_hint=mode_hint,
            ):
                current_output = ""
                if isinstance(chunk, dict):
                    # 计划/执行过程提示（不包含思维链）
                    plan_completed = chunk.get("plan_completed") or []
                    plan_current = chunk.get("plan_current")

                    if plan_current and plan_current != seen_plan_current:
                        seen_plan_current = plan_current
                        current_key = str(plan_current).strip()
                        key = f"current::{current_key}"
                        if not current_key or key in emitted_thinking_keys:
                            continue
                        emitted_thinking_keys.add(key)
                        import json
                        thinking_step_index += 1
                        if first_delta_sent_at is None:
                            first_delta_sent_at = time.perf_counter()
                        delta_count += 1
                        thinking_delta_count += 1
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "delta",
                                "data": f"Step{thinking_step_index}: {plan_current}\n",
                                "isThinking": True,
                                "thinkingFinished": False,
                            }, ensure_ascii=False)
                        }

                    # 已完成事件仅用于进度跟踪，不再推送到前端思考区
                    if len(plan_completed) > last_plan_completed:
                        last_plan_completed = len(plan_completed)

                    current_output = chunk.get("final_answer") or chunk.get("output", "")
                else:
                    current_output = str(chunk)
                if current_output and current_output.startswith(accumulated_output):
                    delta = current_output[len(accumulated_output):]
                    if delta:
                        import json
                        if first_delta_sent_at is None:
                            first_delta_sent_at = time.perf_counter()
                        delta_count += 1
                        answer_delta_count += 1
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
                        final_output_len = len(accumulated_output)

            # 发送完成信号
            import json

            yield {
                "event": "message",
                "data": json.dumps({"type": "done"}, ensure_ascii=False)
            }

            total_ms = (time.perf_counter() - stream_started_at) * 1000
            first_token_ms = (
                (first_delta_sent_at - stream_started_at) * 1000
                if first_delta_sent_at is not None
                else None
            )
            first_token_text = f"{first_token_ms:.0f}ms" if first_token_ms is not None else "N/A"
            print(
                "[Stream Metrics] "
                f"first_token={first_token_text}, "
                f"deltas={delta_count} (thinking={thinking_delta_count}, answer={answer_delta_count}), "
                f"output_len={final_output_len}, total={total_ms:.0f}ms"
            )
            print("[Stream] 流式处理完成")

        except Exception as e:
            print(f"[Stream] 错误: {e}")
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

        print("\n[Graph Sync] 开始同步处理")
        print(f"[Graph Sync] 查询: {_safe_preview(req.query)}...")

        # 同步调用Graph
        result = await run_graph(
            query=req.query,
            chat_history=chat_history,
            mode_hint=None,
        )

        answer = result.get("final_answer", "") or result.get("output", "")

        print("[Graph Sync] 同步处理完成")

        return {
            "answer": answer,
            "route": result.get("route", ""),
            "metadata": result.get("metadata", {}),
        }

    except Exception as e:
        print(f"[Graph Sync] 错误: {e}")
        import traceback
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
