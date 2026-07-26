"""Graph State 定义 - LangGraph 状态管理"""

from typing import TypedDict, List, Dict, Any, Optional


class GraphState(TypedDict):
    """LangGraph 状态定义 - 支持三种模式：常规/深度思考/命理"""

    # ===== 基础输入输出 =====
    query: str                          # 用户查询
    chat_history: List[tuple[str, str]] # 聊天历史 [(role, content), ...]
    mode_hint: Optional[str]            # 模式提示: "fortune" | "research" | None

    # ===== 路由相关 =====
    route: str                          # 路由决策: "default" | "research" | "fortune"
    force_route: Optional[str]          # 强制路由（可选）："default" | "research" | "fortune"

    # ===== 检索相关 =====
    context_docs: List[str]             # 检索到的文档内容
    context: str                        # 格式化后的上下文

    # ===== 工具相关 =====
    tool_results: Dict[str, Any]        # 工具执行结果

    # ===== 计划-执行相关（research）=====
    plan_tasks: List[str]               # 待执行任务清单
    plan_completed: List[str]           # 已完成任务
    plan_current: Optional[str]         # 当前任务
    plan_notes: List[str]               # 执行笔记/证据
    plan_done: bool                     # 是否完成
    plan_iteration: int                 # 已执行轮次
    plan_max_iterations: int            # 最大轮次限制

    # ===== 最终输出 =====
    final_answer: str                   # 最终答案
    output: str                         # 输出（兼容字段）

    # ===== 元数据与错误 =====
    metadata: Dict[str, Any]            # 元数据（包含路由决策信息等）
    intermediate_steps: List[tuple[str, str]]  # 中间步骤
    error: Optional[str]                # 错误信息


def create_graph_state(
    query: str,
    chat_history: list | None = None,
    mode_hint: str | None = None,
    force_route: str | None = None,
) -> GraphState:
    """Create the lightweight runtime state without importing compiled nodes."""
    return {
        "query": query,
        "chat_history": chat_history or [],
        "mode_hint": mode_hint,
        "force_route": force_route,
        "route": "",
        "context_docs": [],
        "context": "",
        "tool_results": {},
        "final_answer": "",
        "output": "",
        "metadata": {},
        "intermediate_steps": [],
        "error": None,
        "plan_tasks": [],
        "plan_completed": [],
        "plan_current": None,
        "plan_notes": [],
        "plan_done": False,
        "plan_iteration": 0,
        "plan_max_iterations": 6,
    }
