"""工具执行节点 - 执行各种工具调用"""

from typing import Dict, Any
from graph.state import GraphState
from agent.tools.date import get_current_date


async def tools_node(state: GraphState) -> Dict[str, Any]:
    """
    工具节点：执行工具调用
    - 根据metadata中的needed_tools执行相应工具
    - 支持多个工具依次执行

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 tool_results
    """
    query = state.get("query", "")
    metadata = state.get("metadata", {})
    needed_tools = metadata.get("needed_tools", [])

    print(f"\n[Tools] 执行工具: {needed_tools}")

    tool_results = {}
    errors = []

    # 执行工具
    for tool_name in needed_tools:
        try:
            print(f"[Tools] 执行: {tool_name}")

            if tool_name == "date":
                result = get_current_date.invoke({})
                tool_results["current_date"] = result
                print(f"[Tools] 日期: {result}")

            elif tool_name == "weather":
                # 需要地点信息，这里简化处理
                result = "请提供城市名称"
                tool_results["weather"] = result
                print(f"[Tools] 天气: {result}")

            # 其他工具可以在这里添加
            # TODO: 添加更多工具支持

        except Exception as e:
            error_msg = f"工具 {tool_name} 执行失败: {str(e)}"
            print(f"[Tools] {error_msg}")
            errors.append(error_msg)
            tool_results[f"{tool_name}_error"] = error_msg

    return {
        **state,
        "tool_results": tool_results,
        "error": "; ".join(errors) if errors else state.get("error"),
    }
