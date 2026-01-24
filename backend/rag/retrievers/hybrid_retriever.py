from __future__ import annotations

from typing import List, Optional, Iterable

from pydantic import Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


def reciprocal_rank_fusion(result_lists: List[List[Document]], k: int = 60) -> List[Document]:
    """
    简单 RRF 融合：对多路检索结果按 1/(k + rank) 加权求和，返回去重后的排序。
    """
    scores: dict[str, float] = {}
    seen: dict[str, Document] = {}
    for results in result_lists:
        for rank, doc in enumerate(results):
            doc_id = doc.metadata.get("id") or doc.metadata.get("source") or str(id(doc))
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id not in seen:
                seen[doc_id] = doc
    # 根据分数降序排列
    merged = sorted(seen.items(), key=lambda x: scores.get(x[0], 0.0), reverse=True)
    return [m[1] for m in merged]


class CrossEncoderReranker:
    """基于 sentence-transformers CrossEncoder 的重排器，可复用。

    当环境无 GPU 时也可在 CPU 运行，但会较慢。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large", top_n: int = 3):
        from sentence_transformers import CrossEncoder  # 延迟导入

        self.top_n = top_n
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: List[Document]) -> List[Document]:
        if not docs:
            return []
        pairs = [[query, d.page_content] for d in docs]
        scores = self.model.predict(pairs).tolist()
        order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
        top = order[: self.top_n]
        return [docs[i] for i in top]


class HybridRetriever(BaseRetriever):
    """多路召回 + 可选交叉重排的通用 Retriever。

    - 接受任意实现 `get_relevant_documents` 的底层 retriever（如向量、BM25 等）
    - 先按各自 top_k 召回，然后做 RRF 融合；
    - 若提供 reranker，则对融合后的前若干再做交叉重排。
    """

    vector_retriever: BaseRetriever
    others: List[BaseRetriever] = Field(default_factory=list)
    fetch_k_each: int = 20
    final_top_k: int = 8
    reranker: Optional[CrossEncoderReranker] = None

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # 各路召回
        all_lists: List[List[Document]] = []
        vec_docs = self.vector_retriever.get_relevant_documents(query)
        all_lists.append(vec_docs)
        for r in self.others:
            try:
                docs = r.get_relevant_documents(query)
            except Exception:
                docs = []
            all_lists.append(docs)
        # RRF 融合
        fused = reciprocal_rank_fusion(all_lists)
        fused = fused[: max(self.final_top_k, 1)]
        # 交叉重排（可选）
        if self.reranker is not None:
            try:
                fused = self.reranker.rerank(query, fused)
            except Exception:
                pass
        return fused


