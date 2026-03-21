"""Graph 构建 - LangGraph 构建器（支持三种模式）"""

from typing import Literal, Dict, Any
from graph.state import GraphState

# 导入所有节点
from .nodes.router import router_node
from .nodes.direct_llm import direct_llm_node
from .nodes.tool_router import tool_router_node
from .nodes.tools_exec import tools_node
from .nodes.rag import rag_node
from .nodes.generate import generate_node
from .nodes.planner import planner_node
from .nodes.executor import executor_node
from .nodes.replanner import replanner_node


def route_after_router(state: GraphState) -> Literal["direct_llm", "tool_router", "rag", "research_planner", "generate", "end"]:
    """
    路由决策：根据router节点的结果决定下一步

    Args:
        state: 当前状态

    Returns:
        str: 下一个节点名称
    """
    route = state.get("route", "default")

    print(f"[Route Decision] 当前路由: {route}")

    if route == "default":
        # 常规模式：走 generate 节点，复用 token 级流式生成能力
        return "generate"
    elif route in ["research", "fortune"]:
        # 深度思考模式和命理模式均采用 Plan-and-Execute
        return "research_planner"
    else:
        # 默认结束
        return "end"


def route_after_tool_router(state: GraphState) -> Literal["tools", "rag", "generate"]:
    """
    工具路由后的决策

    Args:
        state: 当前状态

    Returns:
        str: 下一个节点名称
    """
    metadata = state.get("metadata", {})
    need_tool = metadata.get("need_tool", False)

    if need_tool:
        # 需要工具：先执行工具，再做RAG
        return "tools"
    else:
        # 不需要工具：直接做RAG
        return "rag"


def route_after_replanner(state: GraphState) -> Literal["research_executor", "generate"]:
    """重计划后决定继续执行还是生成答案"""
    if state.get("plan_done"):
        return "generate"
    return "research_executor"


def build_graph():
    """
    构建完整的 LangGraph 工作流

    工作流：
    1. router -> 分析意图，决定路由
    2. direct_llm -> 常规对话（default模式）
    3. tool_router -> 判断是否需要工具（research模式）
    4. tools -> 执行工具调用
    5. rag -> 检索增强（research/fortune模式）
    6. generate -> 生成最终答案

    Returns:
        CompiledGraph: 编译后的图
    """
    try:
        # 尝试使用langgraph
        from langgraph.graph import StateGraph, END

        print("[Graph] 使用 LangGraph 构建")

        # 创建图
        workflow = StateGraph(GraphState)

        # 添加节点
        workflow.add_node("router", router_node)
        workflow.add_node("direct_llm", direct_llm_node)
        workflow.add_node("tool_router", tool_router_node)
        workflow.add_node("tools", tools_node)
        workflow.add_node("rag", rag_node)
        workflow.add_node("generate", generate_node)
        workflow.add_node("research_planner", planner_node)
        workflow.add_node("research_executor", executor_node)
        workflow.add_node("research_replanner", replanner_node)

        # 设置入口点
        workflow.set_entry_point("router")

        # 添加条件边：router -> 根据路由决策
        workflow.add_conditional_edges(
            "router",
            route_after_router,
            {
                "direct_llm": "direct_llm",
                "tool_router": "tool_router",
                "rag": "rag",
                "research_planner": "research_planner",
                "generate": "generate",
                "end": END,
            }
        )

        # 添加条件边：tool_router -> 根据是否需要工具
        workflow.add_conditional_edges(
            "tool_router",
            route_after_tool_router,
            {
                "tools": "tools",
                "rag": "rag",
                "generate": "generate",
            }
        )

        workflow.add_edge("research_planner", "research_executor")
        workflow.add_edge("research_executor", "research_replanner")
        workflow.add_conditional_edges(
            "research_replanner",
            route_after_replanner,
            {
                "research_executor": "research_executor",
                "generate": "generate",
            }
        )

        # 添加固定边
        workflow.add_edge("direct_llm", END)  # 常规模式直接结束
        workflow.add_edge("tools", "rag")      # 工具执行后做RAG
        workflow.add_edge("rag", "generate")   # RAG后生成答案
        workflow.add_edge("generate", END)    # 生成后结束

        # 编译图
        app = workflow.compile()
        print("[Graph] LangGraph 构建成功")

        return app

    except ImportError:
        # langgraph未安装，使用简化版本
        print("[Graph] LangGraph 未安装，使用简化版本")

        class SimpleGraph:
            """简化的Graph实现"""

            async def astream(self, state: Dict[str, Any], stream_mode: str | None = None, **kwargs):
                """流式执行"""
                # 1. Router
                state = await router_node(state)

                # 2. 根据路由执行
                route = state.get("route", "default")

                if route == "default":
                    # 常规模式
                    state = await direct_llm_node(state)
                    yield state

                elif route in ["research", "fortune"]:
                    # 深度思考模式与命理模式（Plan-and-Execute）
                    state = await planner_node(state)
                    while True:
                        state = await executor_node(state)
                        state = await replanner_node(state)
                        if state.get("plan_done"):
                            break
                    async for update in generate_node(state):
                        state = update
                        yield state

            async def ainvoke(self, state: Dict[str, Any]):
                """异步调用"""
                final_state = state
                async for event in self.astream(state):
                    if isinstance(event, dict):
                        final_state = event
                return final_state

        return SimpleGraph()


def create_graph_state(
    query: str,
    chat_history: list = None,
    mode_hint: str = None,
    force_route: str | None = None,
) -> GraphState:
    """
    创建初始Graph状态

    Args:
        query: 用户查询
        chat_history: 聊天历史
        mode_hint: 模式提示

    Returns:
        GraphState: 初始状态
    """
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
