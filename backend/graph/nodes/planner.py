"""计划节点 - 生成任务清单（Plan-and-Execute）"""

from typing import Dict, Any, List
import time

from langchain_community.chat_models import ChatTongyi
from agent.prompts import append_prompt_version, render_prompt
from app.observability import append_model_trace, build_model_trace
from graph.state import GraphState
from app.core.settings import settings


def _parse_tasks(text: str) -> List[str]:
    tasks: List[str] = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        # 支持 "1. xxx" / "1) xxx" / "- xxx"
        if raw[0].isdigit():
            raw = raw.lstrip("0123456789").lstrip(".、)").strip()
        if raw.startswith("-"):
            raw = raw.lstrip("-").strip()
        if raw:
            tasks.append(raw)
    return tasks


async def planner_node(state: GraphState) -> Dict[str, Any]:
    """
    计划节点：把用户目标拆解成可执行任务清单。
    """
    query = state.get("query", "")
    route = state.get("route", "research")
    print(f"\n[Planner] 生成任务清单 (模式: {route}): {query[:50]}...")

    model_name = settings.LLM_MODEL_NAME or "deepseek-v4-flash"
    llm = ChatTongyi(
        model=model_name,
        temperature=0.2,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    prompt_path = (
        "agent/prompts/planner_fortune.txt"
        if route == "fortune"
        else "agent/prompts/planner_research.txt"
    )
    prompt = render_prompt(prompt_path, query=query)
    state = append_prompt_version(
        state,
        stage="planner",
        relative_path=prompt_path,
        rendered_prompt=prompt,
        iteration=0,
    )
    model_started = time.perf_counter()
    try:
        res = await llm.ainvoke(prompt)
        text = getattr(res, "content", str(res))
        state = append_model_trace(
            state,
            build_model_trace(
                stage="planner",
                model_name=model_name,
                started_at=model_started,
                response=res,
                iteration=0,
            ),
        )
    except Exception as e:
        print(f"[Planner] 计划生成失败: {e}")
        text = ""
        state = append_model_trace(
            state,
            build_model_trace(
                stage="planner",
                model_name=model_name,
                started_at=model_started,
                status="failed",
                error_code=type(e).__name__,
                iteration=0,
            ),
        )

    tasks = _parse_tasks(text)
    if not tasks:
        tasks = [f"检索并整理与“{query}”相关的关键资料"]

    return {
        **state,
        "plan_tasks": tasks,
        "plan_completed": [],
        "plan_current": None,
        "plan_notes": [],
        "plan_done": False,
        "plan_iteration": 0,
    }
