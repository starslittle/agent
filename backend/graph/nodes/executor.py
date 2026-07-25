"""执行节点 - 执行计划任务（Plan-and-Execute）"""

from typing import Dict, Any
import json

from langchain_core.messages import HumanMessage
from langchain_community.chat_models import ChatTongyi
from agent.prompts import append_prompt_version, render_prompt
from graph.state import GraphState
from app.core.settings import settings

# 导入可用工具
from agent.tools import (
    get_current_date,
    get_seniverse_weather,
    get_lunar_chart,
    get_ziwei_chart,
    deep_research,
)
from langchain_community.tools.tavily_search import TavilySearchResults

def _get_tool_by_name(name: str):
    tools_map = {
        "get_current_date": get_current_date,
        "get_seniverse_weather": get_seniverse_weather,
        "get_lunar_chart": get_lunar_chart,
        "get_ziwei_chart": get_ziwei_chart,
        "deep_research": deep_research,
        "tavily_search": TavilySearchResults(max_results=5)
    }
    return tools_map.get(name)

async def executor_node(state: GraphState) -> Dict[str, Any]:
    """
    执行节点：负责执行清单中的第一条任务。
    它使用一个轻量级的决策逻辑来决定调用哪个工具。
    """
    plan_tasks = list(state.get("plan_tasks", []))
    plan_completed = list(state.get("plan_completed", []))
    plan_notes = list(state.get("plan_notes", []))
    iteration = int(state.get("plan_iteration", 0))

    if not plan_tasks:
        return {**state, "plan_done": True}

    current_task = plan_tasks.pop(0)
    print(f"\n[Executor] 正在处理子任务: {current_task}")

    # 使用 LLM 决定该任务最适合哪个工具
    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "deepseek-v3.2",
        temperature=0, # 决策需要高确定性
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    tools_desc = """
    1. get_lunar_chart: 用于获取八字、排盘、农历信息。参数需要出生日期等。
    2. get_ziwei_chart: 用于获取紫微斗数排盘信息（命盘、十二宫）。
    3. tavily_search: 用于通用互联网搜索、查询新闻、事实、资料。
    4. get_current_date: 获取当前日期时间。
    5. get_seniverse_weather: 查询天气。
    6. none: 如果不需要工具，直接根据已有信息回答。
    """

    selection_prompt_path = "agent/prompts/executor_tool_selection.txt"
    decision_prompt = render_prompt(
        selection_prompt_path,
        tools_desc=tools_desc.strip(),
        current_task=current_task,
    )
    state = append_prompt_version(
        state,
        stage="executor_tool_selection",
        relative_path=selection_prompt_path,
        rendered_prompt=decision_prompt,
        iteration=iteration + 1,
    )

    try:
        res = llm.invoke([HumanMessage(content=decision_prompt)])
        tool_name = str(res.content).strip().lower()
    except Exception:
        tool_name = "tavily_search" # 默认兜底

    print(f"[Executor] 决策工具: {tool_name}")

    note = ""
    # 执行选定的工具
    if tool_name == "get_lunar_chart":
        # 尝试从查询或任务中提取出生日期/时间/性别/出生地
        extract_prompt_path = "agent/prompts/executor_birth_extract.txt"
        extract_prompt = render_prompt(
            extract_prompt_path,
            query=state.get("query", ""),
            current_task=current_task,
        )
        state = append_prompt_version(
            state,
            stage="executor_birth_extract",
            relative_path=extract_prompt_path,
            rendered_prompt=extract_prompt,
            iteration=iteration + 1,
        )
        try:
            info_res = llm.invoke([HumanMessage(content=extract_prompt)])
            raw = str(info_res.content).strip()
            data = {}
            try:
                data = json.loads(raw)
            except Exception:
                data = {}

            birth_date = str(data.get("birth_date", "")).strip()
            birth_time = str(data.get("birth_time", "")).strip()
            gender = str(data.get("gender", "")).strip()
            birthplace = str(data.get("birthplace", "")).strip()

            print(f"[Executor] 提取到出生日期: {birth_date or '(缺失)'}")

            if not birth_date:
                note = "缺少出生日期，无法进行排盘，请补充 YYYY-MM-DD 格式日期。"
            else:
                payload = {
                    "birth_date": birth_date,
                    "birth_time": birth_time or "00:00",
                    "gender": gender or None,
                    "birthplace": birthplace or None,
                }
                note = get_lunar_chart.invoke(payload)
        except Exception as e:
            note = f"执行排盘失败: {e}"
    elif tool_name == "get_ziwei_chart":
        extract_prompt_path = "agent/prompts/executor_birth_extract.txt"
        extract_prompt = render_prompt(
            extract_prompt_path,
            query=state.get("query", ""),
            current_task=current_task,
        )
        state = append_prompt_version(
            state,
            stage="executor_birth_extract",
            relative_path=extract_prompt_path,
            rendered_prompt=extract_prompt,
            iteration=iteration + 1,
        )
        try:
            info_res = llm.invoke([HumanMessage(content=extract_prompt)])
            raw = str(info_res.content).strip()
            data = {}
            try:
                data = json.loads(raw)
            except Exception:
                data = {}

            birth_date = str(data.get("birth_date", "")).strip()
            birth_time = str(data.get("birth_time", "")).strip()
            gender = str(data.get("gender", "")).strip()
            birthplace = str(data.get("birthplace", "")).strip()

            print(f"[Executor] 提取到出生日期: {birth_date or '(缺失)'}")

            if not birth_date:
                note = "缺少出生日期，无法进行紫微排盘，请补充 YYYY-MM-DD 格式日期。"
            elif not gender:
                note = "缺少性别，无法进行紫微排盘，请补充 男/女。"
            else:
                payload = {
                    "birth_date": birth_date,
                    "birth_time": birth_time or "00:00",
                    "gender": gender,
                    "birthplace": birthplace or None,
                }
                note = get_ziwei_chart.invoke(payload)
        except Exception as e:
            note = f"执行紫微排盘失败: {e}"
    elif "search" in tool_name or tool_name == "tavily_search":
        from langchain_tavily import TavilySearch
        t = TavilySearch(max_results=5)
        try:
            results = t.invoke({"query": current_task})
            # 格式化搜索结果
            lines = []
            for r in (results if isinstance(results, list) else []):
                lines.append(f"- {r.get('title')}: {r.get('content')} ({r.get('url')})")
            note = "\n".join(lines)
        except Exception as e:
            note = f"搜索失败: {e}"
    else:
        note = f"任务完成记录: {current_task} (通过逻辑推理处理)"

    if note:
        plan_notes.append(f"任务: {current_task}\n结果: {note[:500]}...")

    # 更新上下文，供 Generate 节点使用
    context = (state.get("context", "") or "").strip()
    context = (context + "\n\n" if context else "") + f"【子任务执行结果】\n{current_task}: {note}"

    plan_completed.append(current_task)

    return {
        **state,
        "plan_tasks": plan_tasks,
        "plan_completed": plan_completed,
        "plan_current": current_task,
        "plan_notes": plan_notes,
        "plan_iteration": iteration + 1,
        "context": context,
    }
