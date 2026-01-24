"""重计划节点 - 更新任务清单（Plan-and-Execute）"""

from typing import Dict, Any, List

from langchain_community.chat_models import ChatTongyi
from graph.state import GraphState
from app.core.settings import settings


def _parse_tasks(text: str) -> List[str]:
    tasks: List[str] = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw or "没有更多" in raw or "计划完成" in raw:
            continue
        # 提取编号后的内容
        if raw[0].isdigit():
            import re
            raw = re.sub(r'^\d+[\.\)\s、]+', '', raw).strip()
        if raw.startswith("-"):
            raw = raw.lstrip("-").strip()
        if raw:
            tasks.append(raw)
    return tasks


async def replanner_node(state: GraphState) -> Dict[str, Any]:
    """
    重计划节点：根据执行结果检查是否需要调整计划。
    """
    plan_tasks = list(state.get("plan_tasks", []))
    plan_completed = state.get("plan_completed", [])
    plan_notes = state.get("plan_notes", [])
    iteration = int(state.get("plan_iteration", 0))
    max_iterations = int(state.get("plan_max_iterations", 6))
    original_query = state.get("query", "")
    route = state.get("route", "research")

    print(f"\n[🔄 Replanner] 检查进度 (模式: {route}, 第 {iteration} 轮)...")

    # 强制熔断
    if iteration >= max_iterations:
        print("[🔄 Replanner] 已达最大轮次，强制结束。")
        return {**state, "plan_done": True}

    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "qwen-plus-2025-07-28",
        temperature=0.2,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    role_name = "命理项目 Re-planner" if route == "fortune" else "研究项目 Re-planner"

    prompt = f"""
    你是{role_name}。
    
    原始目标：{original_query}
    已完成任务：{plan_completed}
    待办任务：{plan_tasks}
    
    最近获得的证据/结果：
    {" ".join(plan_notes[-3:])}
    
    请根据目前已有的信息，决定下一步：
    1. 如果已有信息足以回答原始目标（例如已获取排盘并完成分析），请回复：【已完成】
    2. 如果现有待办任务仍需执行，请回复：【保持原计划】
    3. 如果发现新情况需要调整，请输出新的“待办任务清单”（编号列表，只列出剩下的步骤）。
    
    你的回复应尽量简短。
    """

    try:
        res = llm.invoke(prompt)
        text = getattr(res, "content", str(res)).strip()
    except Exception as e:
        print(f"[🔄 Replanner] 错误: {e}")
        text = "【保持原计划】"

    if "已完成" in text:
        print("[🔄 Replanner] 目标已达成，进入生成阶段。")
        return {**state, "plan_done": True, "plan_tasks": []}
    
    if "保持原计划" in text:
        print("[🔄 Replanner] 继续按原计划执行。")
        return {**state, "plan_done": False}

    # 否则，解析新的任务清单
    new_tasks = _parse_tasks(text)
    if new_tasks:
        print(f"[🔄 Replanner] 计划已动态调整: {new_tasks}")
        return {**state, "plan_tasks": new_tasks, "plan_done": False}

    return {**state, "plan_done": not plan_tasks}
