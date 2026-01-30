from typing import List

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from langchain_community.chat_models import ChatTongyi
from app.core.settings import settings




def _synthesize_with_llm(prompt: str, model: str = "qwen-plus-2025-07-28") -> str:
    llm = ChatTongyi(model=model, temperature=0.2, dashscope_api_key=settings.DASHSCOPE_API_KEY)
    return llm.invoke(prompt).content  # type: ignore


@tool
def deep_research(topic: str, rounds: int = 2, max_results: int = 3) -> str:
    """
    进行多轮深度检索并汇总要点（轻量版）。
    - topic: 研究主题/问题
    - rounds: 迭代轮数（默认 2，范围 1-5）
    - max_results: 每轮每个子查询最大返回条数（默认 3）
    输出包含要点与引用链接。
    """
    rounds = max(1, min(int(rounds), 5))
    t = TavilySearch(max_results=max_results)
    notes: List[str] = []
    queries = [topic]

    for r in range(rounds):
        new_queries: List[str] = []
        for q in queries:
            try:
                results = t.invoke({"query": q})  # type: ignore
            except Exception:
                results = []
            # 兼容不同返回结构：可能是 list[dict] / {results: list} / list[str]
            try:
                if isinstance(results, dict) and "results" in results:
                    results_iter = results.get("results") or []
                else:
                    results_iter = results or []
            except Exception:
                results_iter = []
            for item in results_iter:
                if isinstance(item, dict):
                    title = item.get("title") or ""
                    content = item.get("content") or item.get("snippet") or ""
                    url = item.get("url") or item.get("link") or ""
                else:
                    s = str(item)
                    title = s[:60]
                    content = s
                    url = ""
                notes.append(f"- {title}\n  摘要: {content}\n  链接: {url}")
        # 基于当前笔记，让 LLM 生成下一轮子问题
        prompt = (
            "你是研究助理。基于以下检索笔记，给出3个更聚焦的子问题（用中文，短句）。\n"
            + "\n".join(notes[-10:])
        )
        try:
            followups = _synthesize_with_llm(prompt)
        except Exception:
            followups = ""
        for line in (followups or "").splitlines():
            line = line.strip("- • \n\t ")
            if len(line) > 0:
                new_queries.append(line)
        if not new_queries:
            break
        queries = new_queries[:3]

    summary_prompt = (
        "请将以下检索笔记汇总为要点列表，给出结论与不确定性，并在每条末尾保留对应链接：\n\n"
        + "\n".join(notes[:50])
    )
    try:
        return _synthesize_with_llm(summary_prompt)
    except Exception:
        return "深度检索完成，但在生成总结时发生错误。以下为原始笔记：\n" + "\n".join(notes[:50])


