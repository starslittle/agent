"""工具路由节点 - 决定是否需要使用工具"""

from typing import Dict, Any
from graph.state import GraphState


async def tool_router_node(state: GraphState) -> Dict[str, Any]:
    """
    工具路由节点：判断是否需要调用工具
    - 分析查询中的关键字
    - 决定是否进入工具执行节点

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 need_tool 标记
    """
    query = state.get("query", "").lower()
    route = state.get("route", "")

    print(f"\n[🔧 Tool Router] 分析是否需要工具...")

    # 工具相关关键字
    tool_keywords = {
        "weather": ["天气", "气温", "温度", "下雨", "晴天", "阴天"],
        "date": ["日期", "今天", "明天", "几号", "星期", "现在"],
        "search": ["搜索", "查找", "查询", "百度", "google"],
        "research": ["研究", "调研", "分析", "深入"],
        "local_kb": ["pdf", "文档", "本地", "文件"],
        "pandas": ["csv", "表格", "数据", "统计"],
    }

    # 检测需要的工具
    needed_tools = []
    for tool_name, keywords in tool_keywords.items():
        if any(keyword in query for keyword in keywords):
            needed_tools.append(tool_name)

    # fortune模式特殊处理
    if route == "fortune":
        needed_tools.append("fortune_rag")

    need_tool = len(needed_tools) > 0

    print(f"[🔧 Tool Router] 需要工具: {needed_tools if need_tool else '无'}")

    return {
        **state,
        "metadata": {
            **state.get("metadata", {}),
            "need_tool": need_tool,
            "needed_tools": needed_tools,
        }
    }
