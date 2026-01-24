"""路由节点 - 意图识别和模式路由"""

from typing import Dict, Any
from graph.state import GraphState
from app.api.intent_router import classify_and_route


async def router_node(state: GraphState) -> Dict[str, Any]:
    """
    路由节点：分析用户输入，决定使用哪种模式
    - default: 常规对话模式
    - research: 深度思考模式（工具+RAG）
    - fortune: 命理模式

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 route 字段
    """
    query = state.get("query", "")
    mode_hint = state.get("mode_hint")
    force_route = state.get("force_route")

    print(f"\n[🔀 Router] 分析查询: {query[:50]}...")
    print(f"[🔀 Router] 模式提示: {mode_hint or 'auto'}")

    try:
        if force_route in {"default", "research", "fortune"}:
            print(f"[🔀 Router] 强制路由: {force_route}")
            return {
                **state,
                "route": force_route,
                "metadata": {
                    **state.get("metadata", {}),
                    "route_type": force_route,
                    "route_forced": True,
                },
            }

        # 使用现有的意图路由器
        routing_result = classify_and_route(query, mode_hint)

        route = routing_result.get("agent_name", "default_llm_agent")
        # 映射到我们的路由类型
        if route == "fortune_agent":
            route_type = "fortune"
        elif route in ["research_agent", "general_rag_agent"]:
            route_type = "research"
        else:
            route_type = "default"

        print(f"[🔀 Router] 路由决策: {route_type}")
        print(f"[🔀 Router] 理由: {routing_result.get('reason', '')}")

        return {
            **state,
            "route": route_type,
            "metadata": {
                **state.get("metadata", {}),
                "route": routing_result,
                "route_type": route_type,
            }
        }

    except Exception as e:
        print(f"[❌ Router] 错误: {e}")
        # 默认使用常规模式
        return {
            **state,
            "route": "default",
            "error": str(e),
        }

