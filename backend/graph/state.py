"""Graph State 定义 - LangGraph 状态管理"""

from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """LangGraph 状态定义 - 支持三种模式：常规/深度思考/命理"""

    # ===== 基础输入输出 =====
    query: str                          # 用户查询
    chat_history: List[tuple[str, str]] # 聊天历史 [(role, content), ...]
    mode_hint: Optional[str]            # 模式提示: "fortune" | "research" | None

    # ===== 路由相关 =====
    route: str                          # 路由决策: "default" | "research" | "fortune"

    # ===== 检索相关 =====
    context_docs: List[str]             # 检索到的文档内容
    context: str                        # 格式化后的上下文

    # ===== 工具相关 =====
    tool_results: Dict[str, Any]        # 工具执行结果

    # ===== 最终输出 =====
    final_answer: str                   # 最终答案
    output: str                         # 输出（兼容字段）

    # ===== 元数据与错误 =====
    metadata: Dict[str, Any]            # 元数据（包含路由决策信息等）
    intermediate_steps: List[tuple[str, str]]  # 中间步骤
    error: Optional[str]                # 错误信息
