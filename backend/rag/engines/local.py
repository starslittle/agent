import logging
from pathlib import Path
from typing import Optional

import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.readers.file import UnstructuredReader
try:
    from llama_index.postprocessor import SentenceTransformerRerank
except Exception:  # 兼容旧版本
    SentenceTransformerRerank = None  # type: ignore


logger = logging.getLogger(__name__)


class LocalEngine:
    name = "local"
    tool_name = "document_analyzer"
    description = "本地非结构化文档（如 PDF/TXT）检索与问答。"

    def __init__(self, config):
        self.config = config

    def _check_data_directory(self) -> bool:
        p = Path(self.config.DATA_DIR)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        return any(p.iterdir())

    def _load_documents(self):
        # 兼容不同版本的 LlamaIndex，直接使用 file_extractor 更稳妥
        file_extractor = {
            ".pdf": UnstructuredReader(ocr_languages=["chi_sim", "eng"], strategy="hi_res"),
        }
        return SimpleDirectoryReader(input_dir=self.config.DATA_DIR, file_extractor=file_extractor).load_data()

    def build(self) -> Optional[BaseQueryEngine]:
        try:
            # 将本地文档向量库存放到独立子目录，避免与其他引擎混用
            chroma_dir = getattr(self.config, "CHROMA_LOCAL_DIR", self.config.CHROMA_DB_DIR)
            chroma_client = chromadb.PersistentClient(path=chroma_dir)
            chroma_collection = chroma_client.get_or_create_collection(self.config.LOCAL_COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            index: Optional[VectorStoreIndex] = None
            if chroma_collection.count() > 0 and Path(chroma_dir).exists():
                index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            else:
                if not self._check_data_directory():
                    logger.info("本地数据目录为空，跳过本地 RAG 构建。")
                    return None
                documents = self._load_documents()
                if not documents:
                    return None
                nodes = SentenceSplitter().get_nodes_from_documents(documents)
                index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)

            if index:
                # 中文优化：MMR + 可选交叉重排
                rerankers = []
                if SentenceTransformerRerank is not None:
                    try:
                        rerankers.append(SentenceTransformerRerank(model="BAAI/bge-reranker-large", top_n=3))
                    except Exception:
                        pass
                return index.as_query_engine(
                    response_mode="compact",
                    similarity_top_k=self.config.SIMILARITY_TOP_K,
                    vector_store_query_mode="mmr",
                    alpha=0.5,
                    node_postprocessors=rerankers or None,
                )
            return None
        except Exception as e:
            logger.error(f"构建本地文档引擎失败: {e}", exc_info=True)
            return None

    def refresh(self) -> bool:
        """增量刷新：将 data/raw 下的最新文档追加到现有索引。

        注意：若无法识别旧文档去重，可能产生重复向量。适合临时增量。
        """
        try:
            chroma_dir = getattr(self.config, "CHROMA_LOCAL_DIR", self.config.CHROMA_DB_DIR)
            chroma_client = chromadb.PersistentClient(path=chroma_dir)
            chroma_collection = chroma_client.get_or_create_collection(self.config.LOCAL_COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

            if chroma_collection.count() == 0:
                # 没有现有索引，则按首次构建处理
                qe = self.build()
                return qe is not None

            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            documents = self._load_documents()
            if not documents:
                logger.info("未发现可加载的本地文档，跳过刷新。")
                return False
            nodes = SentenceSplitter().get_nodes_from_documents(documents)
            try:
                index.insert_nodes(nodes)
            except Exception:
                # 旧版本 API 兼容
                index.refresh(nodes)
            return True
        except Exception as e:
            logger.error(f"刷新本地文档索引失败: {e}", exc_info=True)
            return False


