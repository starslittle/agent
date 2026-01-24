"""生成节点 - 最终答案生成"""

from typing import Dict, Any
from graph.state import GraphState
from langchain_community.chat_models import ChatTongyi
from app.core.settings import settings


async def generation_node(state: GraphState) -> Dict[str, Any]:
    """
    生成节点：基于检索结果和工具调用结果生成最终答案

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态
    """
    # TODO: 实现生成逻辑
    # 1. 整合上下文和工具结果
    # 2. 调用 LLM 生成答案
    # 3. 更新 output 字段

    llm = ChatTongyi(
        model="qwen-plus-2025-07-28",
        temperature=0.2,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )

    # 简单实现（待完善）
    prompt = f"用户问题：{state.get('input', '')}\n上下文：{state.get('context', '')}"

    # response = await llm.ainvoke(prompt)

    return {
        **state,
        "output": "生成的答案（待实现）",
    }
