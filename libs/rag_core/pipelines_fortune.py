from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Tuple

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatTongyi

# 访问项目下的 src 以导入可选的重排器
ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
try:
    from rag.hybrid_retriever import CrossEncoderReranker  # type: ignore
except Exception:  # pragma: no cover - 依赖缺失时降级
    CrossEncoderReranker = None  # type: ignore


DB_DIR = ROOT / "storage" / "chroma" / "fortune"
SUMMARY_COLLECTION = "fortune_summary"
PASSAGE_COLLECTION = "fortune"


def _build_embeddings():
    return HuggingFaceBgeEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        encode_kwargs={"normalize_embeddings": True},
    )


def _open_chroma(collection_name: str):
    return Chroma(
        embedding_function=_build_embeddings(),
        persist_directory=str(DB_DIR),
        collection_name=collection_name,
    )


def _split_sentences(text: str) -> List[str]:
    seps = "。！？!?\n"
    buf: List[str] = []
    sent = []
    for ch in text:
        sent.append(ch)
        if ch in seps:
            s = "".join(sent).strip()
            if s:
                buf.append(s)
            sent = []
    if sent:
        s = "".join(sent).strip()
        if s:
            buf.append(s)
    return buf


def _compress_docs(docs: List[Document], *, budget_chars: int = 1600) -> Tuple[str, List[str]]:
    """将文档压缩为不超过 budget 的句窗文本，并返回引用列表。"""
    parts: List[str] = []
    cites: List[str] = []
    remain = budget_chars
    for d in docs:
        sents = _split_sentences(d.page_content or "")
        snippet = "".join(sents[:4])  # 取前 3-4 句作为句窗
        meta = d.metadata or {}
        cite = f"{Path(str(meta.get('source',''))).name}:{meta.get('parent_id','')}#{meta.get('child_idx','')}"
        snippet = snippet[: min(len(snippet), max(0, remain))]
        if not snippet:
            continue
        parts.append(f"[{cite}] {snippet}")
        cites.append(cite)
        remain -= len(snippet)
        if remain <= 0:
            break
    return "\n".join(parts), cites


def query_fortune(question: str) -> str:
    """双阶段检索 + 简单压缩 + 直接生成（最小可用）。"""
    # 1) 候选章节（摘要库）
    summary_db = _open_chroma(SUMMARY_COLLECTION)
    parents = summary_db.similarity_search(question, k=5)
    parent_ids = {d.metadata.get("parent_id") for d in parents if d.metadata}
    if not parent_ids:
        parent_ids = set()

    # 2) 章节内精检（子块库）
    passage_db = _open_chroma(PASSAGE_COLLECTION)
    # 取较多候选，后续重排
    candidates = passage_db.similarity_search_with_relevance_scores(question, k=20)
    # 过滤到候选章节
    filtered: List[Tuple[Document, float]] = [
        (doc, score) for (doc, score) in candidates if (doc.metadata or {}).get("parent_id") in parent_ids or not parent_ids
    ]
    docs = [d for d, _ in filtered]

    # 3) 可选重排
    if CrossEncoderReranker is not None and docs:
        try:
            reranker = CrossEncoderReranker("BAAI/bge-reranker-base", top_n=min(3, len(docs)))
            docs = reranker.rerank(question, docs)
        except Exception:
            pass
    else:
        # 简单按相关性打分排序（similarity_search_with_relevance_scores 分值越大越相关）
        docs = [d for d, _ in sorted(filtered, key=lambda x: x[1], reverse=True)[:3]]

    # 4) 压缩上下文
    context, cites = _compress_docs(docs, budget_chars=1600)

    # 5) 生成
    prompt_path = ROOT / "backend" / "prompts" / "fortune_prompt.txt"
    if prompt_path.exists():
        sys_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        sys_prompt = (
            "你是命理顾问，根据给定背景资料回答，必须引用出处；若资料不足应明确说明。\n"
            "Final Answer: <回答>\nCitations: <出处列表>\n背景：{context}"
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        ("human", "{question}\n\n{context}"),
    ])
    llm = ChatTongyi(model=os.getenv("FORTUNE_LLM_MODEL", "qwen-turbo"), temperature=0.2, dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""))
    chain = prompt | llm
    result = chain.invoke({"question": question, "context": context})
    return str(getattr(result, "content", result))


