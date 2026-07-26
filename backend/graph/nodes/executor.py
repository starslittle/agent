"""执行节点 - 执行计划任务（Plan-and-Execute）"""

from typing import Dict, Any
import json
import re
import time

from langchain_core.messages import HumanMessage
from langchain_community.chat_models import ChatTongyi
from agent.prompts import append_prompt_version, render_prompt
from app.observability import append_model_trace, build_model_trace
from graph.state import GraphState
from app.core.settings import settings
from agent.tools.registry import get_tool_registry


def _weather_location(text: str) -> str:
    value = re.sub(
        r"(请|帮我|查询|查看|了解|一下|当前|今天|明天|后天|"
        r"未来[一二三四五六七八九十\d]+天|天气|气温|温度|的)",
        "",
        text,
    )
    value = re.sub(r"[，。！？,.!?\s]", "", value)
    return value[:32] or text.strip()


def _normalize_tool_name(raw: str) -> str:
    value = raw.strip().lower().strip("`\"' ")
    allowed = (
        "get_lunar_chart",
        "get_ziwei_chart",
        "get_seniverse_weather",
        "get_current_date",
        "tavily_search",
        "none",
    )
    for name in allowed:
        if value == name or re.search(rf"\b{re.escape(name)}\b", value):
            return name
    return "tavily_search"


async def _invoke_traced(
    llm,
    prompt,
    state: dict[str, Any],
    *,
    stage: str,
    model_name: str,
    iteration: int,
):
    started = time.perf_counter()
    try:
        response = await llm.ainvoke(prompt)
    except Exception as exc:
        return (
            None,
            append_model_trace(
                state,
                build_model_trace(
                    stage=stage,
                    model_name=model_name,
                    started_at=started,
                    status="failed",
                    error_code=type(exc).__name__,
                    iteration=iteration,
                ),
            ),
            exc,
        )
    return (
        response,
        append_model_trace(
            state,
            build_model_trace(
                stage=stage,
                model_name=model_name,
                started_at=started,
                response=response,
                iteration=iteration,
            ),
        ),
        None,
    )


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
    model_name = settings.LLM_MODEL_NAME or "deepseek-v4-flash"
    llm = ChatTongyi(
        model=model_name,
        temperature=0, # 决策需要高确定性
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    tool_registry = get_tool_registry()
    selectable_tools = {
        "get_lunar_chart",
        "get_ziwei_chart",
        "tavily_search",
        "get_current_date",
        "get_seniverse_weather",
    }
    tools_desc = "\n".join(
        f"{index}. {item['name']}: {item['description']}"
        for index, item in enumerate(
            (
                item
                for item in tool_registry.capabilities()
                if item["name"] in selectable_tools
            ),
            start=1,
        )
    )
    tools_desc += "\n6. none: 如果不需要工具，直接根据已有信息回答。"

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

    res, state, decision_error = await _invoke_traced(
        llm,
        [HumanMessage(content=decision_prompt)],
        state,
        stage="executor_tool_selection",
        model_name=model_name,
        iteration=iteration + 1,
    )
    if decision_error is None and res is not None:
        tool_name = _normalize_tool_name(str(res.content))
    else:
        tool_name = "tavily_search" # 默认兜底

    print(f"[Executor] 决策工具: {tool_name}")

    note = ""
    tool_started = time.perf_counter()
    runtime_metadata = dict(state.get("metadata", {}))
    execution_id = str(runtime_metadata.get("execution_id") or "legacy")
    cancel_event = runtime_metadata.get("cancel_event")
    shadow = bool(runtime_metadata.get("shadow", False))
    tool_audit_events = list(runtime_metadata.get("tool_audit_events", []))
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
            info_res, state, extract_error = await _invoke_traced(
                llm,
                [HumanMessage(content=extract_prompt)],
                state,
                stage="executor_birth_extract",
                model_name=model_name,
                iteration=iteration + 1,
            )
            if extract_error is not None or info_res is None:
                raise extract_error or RuntimeError("birth extraction failed")
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
                note = await tool_registry.execute(
                    "get_lunar_chart",
                    payload,
                    execution_id=execution_id,
                    shadow=shadow,
                    cancel_event=cancel_event,
                    audit_events=tool_audit_events,
                )
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
            info_res, state, extract_error = await _invoke_traced(
                llm,
                [HumanMessage(content=extract_prompt)],
                state,
                stage="executor_birth_extract",
                model_name=model_name,
                iteration=iteration + 1,
            )
            if extract_error is not None or info_res is None:
                raise extract_error or RuntimeError("birth extraction failed")
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
                note = await tool_registry.execute(
                    "get_ziwei_chart",
                    payload,
                    execution_id=execution_id,
                    shadow=shadow,
                    cancel_event=cancel_event,
                    audit_events=tool_audit_events,
                )
        except Exception as e:
            note = f"执行紫微排盘失败: {e}"
    elif tool_name == "get_current_date":
        try:
            note = await tool_registry.execute(
                "get_current_date",
                {},
                execution_id=execution_id,
                shadow=shadow,
                cancel_event=cancel_event,
                audit_events=tool_audit_events,
            )
        except Exception as e:
            note = f"日期查询失败: {e}"
    elif tool_name == "get_seniverse_weather":
        try:
            note = await tool_registry.execute(
                "get_seniverse_weather",
                {"location": _weather_location(current_task)},
                execution_id=execution_id,
                shadow=shadow,
                cancel_event=cancel_event,
                audit_events=tool_audit_events,
            )
        except Exception as e:
            note = f"天气查询失败: {e}"
    elif "search" in tool_name or tool_name == "tavily_search":
        try:
            note = await tool_registry.execute(
                "tavily_search",
                {"query": current_task, "max_results": 5},
                execution_id=execution_id,
                shadow=shadow,
                cancel_event=cancel_event,
                audit_events=tool_audit_events,
            )
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
    final_metadata = dict(state.get("metadata", {}))
    tool_traces = list(final_metadata.get("tool_traces", []))
    if tool_name != "none":
        tool_traces.append(
            {
                "name": tool_name,
                "iteration": iteration + 1,
                "status": (
                    "failed"
                    if "失败" in note or note.startswith("错误")
                    else "completed"
                ),
                "duration_ms": int((time.perf_counter() - tool_started) * 1000),
            }
        )
    final_metadata["tool_traces"] = tool_traces
    final_metadata["tool_audit_events"] = tool_audit_events

    return {
        **state,
        "plan_tasks": plan_tasks,
        "plan_completed": plan_completed,
        "plan_current": current_task,
        "plan_notes": plan_notes,
        "plan_iteration": iteration + 1,
        "context": context,
        "metadata": final_metadata,
    }
