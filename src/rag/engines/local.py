import logging
from pathlib import Path
from typing import Optional

import chromadb
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.readers import ReaderConfig
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.readers.file import UnstructuredReader


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
        reader_config = ReaderConfig(
            reader_by_ext={
                ".pdf": UnstructuredReader(),
            },
            unstructured_reader_config={"languages": ["chi_sim", "eng"]},
        )
        return SimpleDirectoryReader(input_dir=self.config.DATA_DIR, reader_config=reader_config).load_data()

    def build(self) -> Optional[BaseQueryEngine]:
        try:
            chroma_client = chromadb.PersistentClient(path=self.config.CHROMA_DB_DIR)
            chroma_collection = chroma_client.get_or_create_collection(self.config.LOCAL_COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            index: Optional[VectorStoreIndex] = None
            if chroma_collection.count() > 0 and Path(self.config.CHROMA_DB_DIR).exists():
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
                return index.as_query_engine(
                    response_mode="compact",
                    similarity_top_k=self.config.SIMILARITY_TOP_K,
                )
            return None
        except Exception as e:
            logger.error(f"构建本地文档引擎失败: {e}", exc_info=True)
            return None


