"""计划节点 - 生成任务清单（Plan-and-Execute）"""

from typing import Dict, Any, List

from langchain_community.chat_models import ChatTongyi
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
    print(f"\n[🧭 Planner] 生成任务清单 (模式: {route}): {query[:50]}...")

    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "qwen-plus-2025-07-28",
        temperature=0.2,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    if route == "fortune":
        system_role = "你是命理分析专家，精通紫微斗数、八字命理及易经分析。"
        instruction = "请根据用户的问题，规划出获取排盘、检索命理典籍、分析吉凶运势、给出建议等 3-6 个执行步骤。"
    else:
        system_role = "你是研究计划专家。"
        instruction = "请把下面的目标拆解成 3-6 条可执行任务清单。"

    prompt = (
        f"{system_role}{instruction}\n"
        "只输出编号列表（如 1. ... 2. ...），不要输出其他内容。\n\n"
        f"目标：{query}\n"
    )
    try:
        res = llm.invoke(prompt)
        text = getattr(res, "content", str(res))
    except Exception as e:
        print(f"[🧭 Planner] 计划生成失败: {e}")
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
