import os
import sys
import logging
from pathlib import Path
from typing import List, Optional

import chromadb
import requests
import pandas as pd

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Settings,
    StorageContext,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core.readers import ReaderConfig

from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.readers.file import UnstructuredReader
try:
    from llama_index.readers.notion import NotionPageReader, NotionDatabaseReader  # type: ignore
    HAS_DB_READER = True
except Exception:
    from llama_index.readers.notion import NotionPageReader  # type: ignore
    NotionDatabaseReader = None  # type: ignore
    HAS_DB_READER = False
from llama_index.experimental.query_engine import PandasQueryEngine


# 基础路径（项目根）
BASE_DIR = Path(__file__).resolve().parents[2]


def _format_uuid_with_hyphens(uuid_str: str) -> str:
    s = (uuid_str or "").strip()
    if not s:
        return s
    if "-" in s:
        return s
    if len(s) == 32:
        return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"
    return s


def _fetch_page_ids_from_database(notion_api_key: str, database_id: str) -> List[str]:
    """在缺少 NotionDatabaseReader 时，通过官方 API 枚举数据库下的页面 id。"""
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    did = _format_uuid_with_hyphens(database_id)
    url = f"https://api.notion.com/v1/databases/{did}/query"
    try:
        resp = requests.post(url, headers=headers, json={"page_size": 100}, timeout=60)
        if resp.status_code >= 400:
            logger.warning(f"列举数据库页面失败: {resp.status_code} {resp.text}")
            return []
        data = resp.json()
        ids = [x.get("id") for x in data.get("results", []) if x.get("id")]
        return ids
    except Exception as e:
        logger.warning(f"请求数据库页面列表失败: {e}")
        return []


class RAGConfig:
    # API 和模型配置
    DASHSCOPE_API_KEY: str = os.environ.get("DASHSCOPE_API_KEY", "")
    LLM_MODEL_NAME: str = "qwen-plus"
    EMBED_MODEL_NAME: str = "BAAI/bge-small-zh-v1.5"

    # RAG 系统配置
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 20
    SIMILARITY_TOP_K: int = 3

    # 路径配置（绝对路径）
    DATA_DIR: str = str(BASE_DIR / "data" / "raw")
    CHROMA_DB_DIR: str = str(BASE_DIR / "storage" / "chroma")
    LOCAL_COLLECTION_NAME: str = "local"
    NOTION_COLLECTION_NAME: str = "notion"
    CSV_FILE_PATH: str = str(BASE_DIR / "data" / "sales_data.csv")

    # Notion 配置
    ENABLE_NOTION: bool = os.environ.get("ENABLE_NOTION", "0").lower() in ("1", "true", "yes")
    NOTION_API_KEY: str = os.environ.get("NOTION_API_KEY", "")
    NOTION_PAGE_IDS: List[str] = (
        [pid.strip() for pid in os.environ.get("NOTION_PAGE_IDS", "").split(",") if pid.strip()]
        if os.environ.get("NOTION_PAGE_IDS")
        else []
    )
    NOTION_DATABASE_ID: str = os.environ.get("NOTION_DATABASE_ID", "")


logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGSystem:
    def __init__(self, config: RAGConfig):
        self.config = config
        self._setup_settings()
        self.rag_query_engine: Optional[BaseQueryEngine] = None
        self.notion_query_engine: Optional[BaseQueryEngine] = None
        self.pandas_query_engine: Optional[BaseQueryEngine] = None
        self.tools: List[QueryEngineTool] = []

    def _setup_settings(self):
        logger.info("正在配置全局Settings…")
        if not self.config.DASHSCOPE_API_KEY:
            logger.warning("DASHSCOPE_API_KEY 未设置。")
        Settings.llm = DashScope(
            model=self.config.LLM_MODEL_NAME,
            temperature=0.7,
            api_key=self.config.DASHSCOPE_API_KEY,
        )
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=self.config.EMBED_MODEL_NAME
        )
        Settings.chunk_size = self.config.CHUNK_SIZE
        Settings.chunk_overlap = self.config.CHUNK_OVERLAP

    def _build_local_rag_engine(self):
        logger.info("--- 构建/加载 本地文档 RAG 引擎 ---")
        chroma_client = chromadb.PersistentClient(path=self.config.CHROMA_DB_DIR)
        chroma_collection = chroma_client.get_or_create_collection(self.config.LOCAL_COLLECTION_NAME)
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        index: Optional[VectorStoreIndex] = None
        if chroma_collection.count() > 0 and Path(self.config.CHROMA_DB_DIR).exists():
            logger.info("检测到现有本地集合，直接加载索引…")
            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        else:
            if not self._check_data_directory():
                logger.warning("本地数据目录为空，跳过本地 RAG 构建。")
                return
            documents = self._load_documents()
            if not documents:
                return
            nodes = SentenceSplitter().get_nodes_from_documents(documents)
            index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)
        if index:
            self.rag_query_engine = index.as_query_engine(
                response_mode="compact",
                similarity_top_k=self.config.SIMILARITY_TOP_K,
            )

    def _build_notion_engine(self):
        if not self.config.ENABLE_NOTION:
            logger.info("未启用 Notion 集成，跳过构建 Notion 引擎。")
            return
        if not self.config.NOTION_API_KEY:
            logger.warning("未设置 NOTION_API_KEY，跳过 Notion 引擎构建。")
            return
        logger.info("--- 构建/加载 Notion RAG 引擎 ---")
        try:
            chroma_client = chromadb.PersistentClient(path=self.config.CHROMA_DB_DIR)
            chroma_collection = chroma_client.get_or_create_collection(self.config.NOTION_COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            index: Optional[VectorStoreIndex] = None
            if chroma_collection.count() > 0 and Path(self.config.CHROMA_DB_DIR).exists():
                logger.info("检测到现有 Notion 集合，直接加载索引…")
                index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            else:
                logger.info("未发现 Notion 索引，调用 Notion API 拉取数据并创建…")
                documents = []
                if self.config.NOTION_PAGE_IDS:
                    page_reader = NotionPageReader(integration_token=self.config.NOTION_API_KEY)
                    documents.extend(page_reader.load_data(page_ids=self.config.NOTION_PAGE_IDS) or [])
                if self.config.NOTION_DATABASE_ID:
                    if HAS_DB_READER and NotionDatabaseReader is not None:
                        db_reader = NotionDatabaseReader(integration_token=self.config.NOTION_API_KEY)
                        documents.extend(db_reader.load_data(database_id=_format_uuid_with_hyphens(self.config.NOTION_DATABASE_ID)) or [])
                    else:
                        # 兼容没有 NotionDatabaseReader 的版本：直接用官方 API 查询数据库下页面，再用 NotionPageReader 拉取
                        page_ids = _fetch_page_ids_from_database(self.config.NOTION_API_KEY, self.config.NOTION_DATABASE_ID)
                        if page_ids:
                            page_reader = NotionPageReader(integration_token=self.config.NOTION_API_KEY)
                            documents.extend(page_reader.load_data(page_ids=page_ids) or [])
                        else:
                            logger.warning("无法通过数据库ID获取页面列表，可能是权限/ID 无效或数据库为空。")
                if not documents:
                    logger.warning("未从 Notion 拉取到任何文档，跳过 Notion 引擎创建。")
                    return
                nodes = SentenceSplitter().get_nodes_from_documents(documents)
                index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)
            if index:
                self.notion_query_engine = index.as_query_engine(
                    response_mode="compact",
                    similarity_top_k=self.config.SIMILARITY_TOP_K,
                )
        except Exception as e:
            logger.error(f"构建 Notion 引擎时出错: {e}")
            import traceback
            traceback.print_exc()

    def _build_pandas_engine(self):
        if not Path(self.config.CSV_FILE_PATH).exists():
            logger.info("CSV 文件不存在，跳过 Pandas 引擎。")
            return
        try:
            df = pd.read_csv(self.config.CSV_FILE_PATH)
            self.pandas_query_engine = PandasQueryEngine(
                df=df,
                verbose=True,
                instructional_prompt="请严格根据指令生成Python代码来回答问题。",
            )
        except Exception as e:
            logger.error(f"创建 Pandas 引擎时出错: {e}")

    def _setup_tools(self):
        self.tools = []
        if self.rag_query_engine:
            self.tools.append(
                QueryEngineTool(
                    query_engine=self.rag_query_engine,
                    metadata=ToolMetadata(
                        name="document_analyzer",
                        description="本地非结构化文档（如 PDF/TXT）检索与问答。",
                    ),
                )
            )
        if self.notion_query_engine:
            self.tools.append(
                QueryEngineTool(
                    query_engine=self.notion_query_engine,
                    metadata=ToolMetadata(
                        name="notion_knowledge_base",
                        description="Notion 工作区知识库检索与问答。",
                    ),
                )
            )
        if self.pandas_query_engine:
            self.tools.append(
                QueryEngineTool(
                    query_engine=self.pandas_query_engine,
                    metadata=ToolMetadata(
                        name="sales_data_analyzer",
                        description="CSV 销售数据的查询与分析。",
                    ),
                )
            )

    def _check_data_directory(self) -> bool:
        p = Path(self.config.DATA_DIR)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        return any(p.iterdir())

    def _load_documents(self):
        try:
            reader_config = ReaderConfig(
                reader_by_ext={
                    ".pdf": UnstructuredReader(),
                },
                unstructured_reader_config={"languages": ["chi_sim", "eng"]},
            )
            documents = SimpleDirectoryReader(input_dir=self.config.DATA_DIR, reader_config=reader_config).load_data()
            if not documents:
                return None
            return documents
        except Exception as e:
            logger.error(f"加载本地文档失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def startup(self):
        self._build_local_rag_engine()
        self._build_notion_engine()
        self._build_pandas_engine()
        self._setup_tools()

    def get_query_engine(self, source: str = "notion") -> Optional[BaseQueryEngine]:
        source = (source or "notion").lower()
        if source == "notion":
            return self.notion_query_engine
        if source == "local":
            return self.rag_query_engine
        if source == "pandas":
            return self.pandas_query_engine
        return None
