from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple, Any, Dict

from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatTongyi

from app.core.settings import settings

try:
    from .hybrid_retriever import CrossEncoderReranker  # type: ignore
except Exception:  # pragma: no cover
    CrossEncoderReranker = None  # type: ignore


ROOT = Path(__file__).resolve().parents[2]
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
    parts: List[str] = []
    cites: List[str] = []
    remain = budget_chars
    for d in docs:
        sents = _split_sentences(d.page_content or "")
        snippet = "".join(sents[:4])
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


def query_fortune(question: str, *, return_meta: bool = False) -> Any:
    def _expand_queries(llm: ChatTongyi, q: str) -> List[str]:
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "请把用户问题改写为 2-3 条中文检索查询，尽量覆盖：核心对象A、条件/情境B、以及‘A在B情况下/与B组合’。每行一条，短句，不要编号。"),
                ("human", "问题：{q}"),
            ])
            text = (prompt | llm).invoke({"q": q})
            out = getattr(text, "content", str(text))
            lines = [l.strip().lstrip("-•").strip() for l in out.splitlines() if l.strip()]
            merged: List[str] = []
            for s in [q] + lines:
                if s and s not in merged:
                    merged.append(s)
            return merged[:4]
        except Exception:
            return [q]

    api_key = settings.DASHSCOPE_API_KEY or ""
    streaming_enabled = bool(api_key)
    llm = ChatTongyi(
        model=(settings.FORTUNE_LLM_MODEL or "qwen-plus-2025-07-28"),
        temperature=0.2,
        dashscope_api_key=api_key,
        streaming=streaming_enabled,
    )

    queries = _expand_queries(llm, question)

    summary_db = _open_chroma(SUMMARY_COLLECTION)
    parents: List[Document] = []
    for q in queries:
        try:
            parents.extend(summary_db.similarity_search(q, k=3))
        except Exception:
            continue
    parent_ids = {d.metadata.get("parent_id") for d in parents if d.metadata}
    if not parent_ids:
        parent_ids = set()

    passage_db = _open_chroma(PASSAGE_COLLECTION)
    all_candidates: List[Tuple[Document, float]] = []
    for q in queries:
        try:
            all_candidates.extend(passage_db.similarity_search_with_relevance_scores(q, k=10))
        except Exception:
            continue

    def _uid(d: Document) -> str:
        m = d.metadata or {}
        return f"{m.get('source','')}|{m.get('parent_id','')}|{m.get('child_idx','')}"

    filtered: List[Tuple[Document, float]] = []
    seen: set[str] = set()
    for doc, score in all_candidates:
        if parent_ids and (doc.metadata or {}).get("parent_id") not in parent_ids:
            continue
        key = _uid(doc)
        if key in seen:
            continue
        seen.add(key)
        filtered.append((doc, score))

    docs = [d for d, _ in filtered]
    if CrossEncoderReranker is not None and docs:
        try:
            reranker = CrossEncoderReranker("BAAI/bge-reranker-base", top_n=min(3, len(docs)))
            docs = reranker.rerank(question, docs)
        except Exception:
            pass
    else:
        docs = [d for d, _ in sorted(filtered, key=lambda x: x[1], reverse=True)[:3]]

    context, cites = _compress_docs(docs, budget_chars=1600)

    prompt_path = ROOT / "prompts" / "fortune_prompt.txt"
    if not prompt_path.exists():
        prompt_path = ROOT / "backend" / "prompts" / "fortune_prompt.txt"
    if prompt_path.exists():
        sys_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        sys_prompt = (
            "你是命理顾问，根据给定背景资料回答；若资料未直接描述组合情形，允许基于各自定义与方法进行合理推断，但需标注为‘推断’，并说明依据。\n"
            "Final Answer: <回答>\n背景：{context}"
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        ("human", "{question}\n\n{context}"),
    ])
    chain = prompt | llm
    result = chain.invoke({"question": question, "context": context})
    answer_text = str(getattr(result, "content", result))

    if not return_meta:
        return answer_text

    meta: Dict[str, Any] = {
        "answer": answer_text,
        "queries": queries,
        "parents": [d.metadata.get("parent_id") for d in parents if d.metadata],
        "passages": [((d.metadata or {}).get("parent_id"), (d.metadata or {}).get("child_idx")) for d in docs],
        "context": context,
    }
    return meta


