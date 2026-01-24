"""RAG节点 - 检索增强生成"""

from typing import Dict, Any, List
from graph.state import GraphState
from rag.pipelines import query as rag_query
from rag.pipelines import query_fortune
from langchain_community.chat_models import ChatTongyi
from langchain_tavily import TavilySearch
from app.core.settings import settings


def _grade_context(question: str, context: str) -> bool:
    """判断内部检索内容是否足够回答问题。"""
    prompt = (
        "你是检索质量评估器。判断给定【检索内容】是否足以回答【用户问题】。\n"
        "只回答 YES 或 NO，不要输出其他内容。\n\n"
        f"用户问题：{question}\n\n"
        f"检索内容：{context}\n"
    )
    llm = ChatTongyi(
        model=settings.LLM_MODEL_NAME or "qwen-plus-2025-07-28",
        temperature=0.0,
        dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
    )
    try:
        res = llm.invoke(prompt)
        text = getattr(res, "content", str(res)).strip().upper()
        return text.startswith("YES")
    except Exception:
        # 保守策略：失败时认为不足，触发外部检索
        return False


def _web_search(query: str, max_results: int = 5) -> str:
    """使用 Tavily 进行网络搜索并格式化结果。"""
    t = TavilySearch(max_results=max_results)
    try:
        results = t.invoke({"query": query})  # type: ignore
    except Exception:
        results = []
    try:
        if isinstance(results, dict) and "results" in results:
            items = results.get("results") or []
        else:
            items = results or []
    except Exception:
        items = []
    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title") or ""
            content = item.get("content") or item.get("snippet") or ""
            url = item.get("url") or item.get("link") or ""
        else:
            s = str(item)
            title = s[:60]
            content = s
            url = ""
        lines.append(f"- 标题: {title}\n  摘要: {content}\n  链接: {url}")
    return "\n".join(lines).strip()

async def rag_node(state: GraphState) -> Dict[str, Any]:
    """
    RAG节点：根据路由类型执行相应的RAG检索（已临时停用，代码已注释）
    """
    print(f"\n[📚 RAG] RAG 已全局停用，跳过检索")
    return {
        **state,
        "context_docs": [],
        "context": "",
    }

    # --- 以下为原 RAG 逻辑，已注释备用 ---
    # user_query = state.get("query", "")
    # route = state.get("route", "")
    #
    # print(f"\n[📚 RAG] 执行检索，模式: {route}")
    #
    # try:
    #     context_docs = []
    #     context = ""
    #
    #     if route == "fortune":
    #         # 命理RAG
    #         print(f"[📚 RAG] 使用命理RAG")
    #         result = query_fortune(user_query, return_meta=True)
    #         if isinstance(result, dict):
    #             context = result.get("context", "")
    #             context_docs = result.get("passages", [])
    #         else:
    #             context = str(result)
    #
    #         # CRAG: 评估内部检索是否足够，必要时触发外部搜索
    #         sufficient = _grade_context(user_query, context)
    #         if not sufficient:
    #             print("[📚 RAG] 内部检索不足，触发外部搜索")
    #             web_context = _web_search(user_query)
    #             if web_context:
    #                 context = (
    #                     (context + "\n\n" if context else "")
    #                     + "【外部检索结果】\n"
    #                     + web_context
    #                 )
    #
    #     elif route == "research":
    #         # 通用RAG
    #         print(f"[📚 RAG] 使用通用RAG")
    #         # 从状态中获取聊天历史并传递给 rag_query
    #         chat_history = state.get("chat_history", [])
    #         context = rag_query(user_query, chat_history=chat_history)
    #         context_docs = [] # 通用RAG暂不返回文档列表
    #
    #     else:
    #         # 默认不检索
    #         print(f"[📚 RAG] 跳过检索")
    #         context_docs = []
    #         context = ""
    #
    #     return {
    #         **state,
    #         "context_docs": context_docs,
    #         "context": context,
    #     }
    #
    # except Exception as e:
    #     print(f"[❌ RAG] 错误: {e}")
    #     import traceback
    #     traceback.print_exc()
    #
    #     return {
    #         **state,
    #         "context_docs": [],
    #         "context": "",
    #         "error": str(e),
    #     }
