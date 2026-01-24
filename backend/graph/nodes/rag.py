"""RAG节点 - 检索增强生成"""

from typing import Dict, Any
from graph.state import GraphState
from rag.pipelines import query as rag_query
from rag.pipelines import query_fortune

async def rag_node(state: GraphState) -> Dict[str, Any]:
    """
    RAG节点：根据路由类型执行相应的RAG检索
    - research模式：通用RAG
    - fortune模式：命理RAG
    - local模式：本地文档RAG

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 context 和 context_docs
    """
    user_query = state.get("query", "")
    route = state.get("route", "")

    print(f"\n[📚 RAG] 执行检索，模式: {route}")

    try:
        context_docs = []
        context = ""

        if route == "fortune":
            # 命理RAG
            print(f"[📚 RAG] 使用命理RAG")
            result = query_fortune(user_query, return_meta=True)
            if isinstance(result, dict):
                context = result.get("context", "")
                context_docs = result.get("passages", [])
            else:
                context = str(result)

        elif route == "research":
            # 通用RAG
            print(f"[📚 RAG] 使用通用RAG")
            # 从状态中获取聊天历史并传递给 rag_query
            chat_history = state.get("chat_history", [])
            context = rag_query(user_query, chat_history=chat_history)
            context_docs = [] # 通用RAG暂不返回文档列表

        else:
            # 默认不检索
            print(f"[📚 RAG] 跳过检索")
            context_docs = []
            context = ""

        return {
            **state,
            "context_docs": context_docs,
            "context": context,
        }

    except Exception as e:
        print(f"[❌ RAG] 错误: {e}")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "context_docs": [],
            "context": "",
            "error": str(e),
        }
