"""计划节点 - 生成任务清单（Plan-and-Execute）"""

from typing import Dict, Any, List

from langchain_community.chat_models import ChatTongyi
from agent.prompts import append_prompt_version, render_prompt
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

    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "deepseek-v4-flash",
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
    try:
        res = llm.invoke(prompt)
        text = getattr(res, "content", str(res))
    except Exception as e:
        print(f"[Planner] 计划生成失败: {e}")
        text = ""

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
