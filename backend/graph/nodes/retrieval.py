"""检索节点 - RAG 检索（保留用于兼容）"""

from typing import Dict, Any
from graph.state import GraphState
from .rag import rag_node


# 检索节点现在使用rag_node
async def retrieval_node(state: GraphState) -> Dict[str, Any]:
    """
    检索节点：从知识库中检索相关文档
    （此节点已由 rag_node 替代，保留用于兼容）

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态
    """
    return await rag_node(state)

