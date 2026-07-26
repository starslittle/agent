"""LangGraph 图与节点"""

from importlib import import_module

__all__ = [
    "GraphState",
    "build_graph",
    "create_graph_state",
    "run_graph",
    "stream_graph",
]

from .state import GraphState, create_graph_state
from .nodes.router import router_node
from .nodes.planner import planner_node
from .nodes.executor import executor_node
from .nodes.replanner import replanner_node
from .nodes.generate import generate_node


# 全局Graph实例
_graph_instance = None


def get_graph():
    """获取全局Graph实例（单例）"""
    global _graph_instance
    if _graph_instance is None:
        from .builder import build_graph

        _graph_instance = build_graph()
    return _graph_instance


async def run_graph(
    query: str,
    chat_history: list = None,
    mode_hint: str = None,
    force_route: str | None = None,
):
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
    state = create_graph_state(query, chat_history, mode_hint, force_route)
    state["metadata"] = {**state.get("metadata", {}), "streaming": True}

    result = await graph.ainvoke(state)
    return result


async def stream_graph(
    query: str,
    chat_history: list = None,
    mode_hint: str = None,
    force_route: str | None = None,
    runtime_metadata: dict | None = None,
):
    """
    流式运行Graph

    Args:
        query: 用户查询
        chat_history: 聊天历史
        mode_hint: 模式提示

    Yields:
        dict: 流式输出片段
    """
    state = create_graph_state(query, chat_history, mode_hint, force_route)
    state["metadata"] = {
        **state.get("metadata", {}),
        **(runtime_metadata or {}),
        "streaming": True,
    }
    # 统一走手写流式编排，确保所有模式都可增量输出
    state = await router_node(state)
    route = state.get("route", "default")

    # default/research/fortune 的最终回答统一通过 generate_node 产出
    if route == "default":
        async for update in generate_node(state):
            state = update
            yield state
        return

    if route in ["research", "fortune"]:
        state = await planner_node(state)
        yield state
        while True:
            state = await executor_node(state)
            yield state
            state = await replanner_node(state)
            yield state
            if state.get("plan_done"):
                break

        async for update in generate_node(state):
            state = update
            yield state
        return

    # 未识别路由时兜底：直接流式生成
    async for update in generate_node(state):
        state = update
        yield state


def __getattr__(name: str):
    if name == "build_graph":
        value = getattr(import_module("graph.builder"), name)
        globals()[name] = value
        return value
    raise AttributeError(name)
