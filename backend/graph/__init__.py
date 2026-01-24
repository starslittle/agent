"""LangGraph 图与节点"""

__all__ = [
    "GraphState",
    "build_graph",
    "create_graph_state",
    "run_graph",
    "stream_graph",
]

from .state import GraphState
from .builder import build_graph, create_graph_state


# 全局Graph实例
_graph_instance = None


def get_graph():
    """获取全局Graph实例（单例）"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


async def run_graph(query: str, chat_history: list = None, mode_hint: str = None):
    """
    运行Graph（同步调用）

    Args:
        query: 用户查询
        chat_history: 聊天历史
        mode_hint: 模式提示

    Returns:
        dict: 包含最终答案的字典
    """
    graph = get_graph()
    state = create_graph_state(query, chat_history, mode_hint)

    result = await graph.ainvoke(state)
    return result


async def stream_graph(query: str, chat_history: list = None, mode_hint: str = None):
    """
    流式运行Graph

    Args:
        query: 用户查询
        chat_history: 聊天历史
        mode_hint: 模式提示

    Yields:
        dict: 流式输出片段
    """
    result = await run_graph(query, chat_history, mode_hint)
    answer = result.get("final_answer", "") or result.get("output", "")

    if not answer:
        yield result
        return

    # 分片输出，确保前端体验为流式
    chunk_size = 20
    for i in range(0, len(answer), chunk_size):
        partial = answer[: i + chunk_size]
        yield {
            **result,
            "final_answer": partial,
            "output": partial,
        }
