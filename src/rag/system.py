import os
import sys
import logging
from pathlib import Path
from typing import List, Optional

import chromadb
import requests
import pandas as pd

from llama_index.core import Settings
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# 新增：引擎模块
from rag.engines.local import LocalEngine
from rag.engines.notion import NotionEngine
from rag.engines.pandas_engine import PandasEngine


# 基础路径（项目根）
BASE_DIR = Path(__file__).resolve().parents[2]

# 兜底加载根目录 .env，确保在读取环境变量前完成加载
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=str(BASE_DIR / ".env"))
except Exception:
    pass


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
    # 更适合中文的默认切分与召回参数
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 80
    SIMILARITY_TOP_K: int = 8

    # 路径配置（绝对路径）
    DATA_DIR: str = str(BASE_DIR / "data" / "raw")
    # 旧字段（兼容）
    CHROMA_DB_DIR: str = str(BASE_DIR / "storage" / "chroma")
    # 新字段：将不同引擎的向量库分目录存放
    CHROMA_BASE_DIR: str = str(BASE_DIR / "storage" / "chroma")
    CHROMA_LOCAL_DIR: str = str(BASE_DIR / "storage" / "chroma" / "local")
    CHROMA_NOTION_DIR: str = str(BASE_DIR / "storage" / "chroma" / "notion")
    LOCAL_COLLECTION_NAME: str = "local"
    NOTION_COLLECTION_NAME: str = "notion"
    # 允许通过环境变量 CSV_FILE_PATH 指定 CSV 路径；默认指向 data/raw 目录
    CSV_FILE_PATH: str = os.environ.get(
        "CSV_FILE_PATH",
        str(BASE_DIR / "data" / "sales_data.csv"),
    )
    CSV_DIR_PATH: str = os.environ.get(
        "CSV_DIR_PATH",
        str(BASE_DIR / "data" / "raw"),
    )

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
        self.rag_query_engine = LocalEngine(self.config).build()

    def _build_notion_engine(self):
        logger.info("--- 构建/加载 Notion RAG 引擎 ---")
        self.notion_query_engine = NotionEngine(self.config).build()

    def _build_pandas_engine(self):
        logger.info("--- 构建/加载 Pandas 数据查询引擎 ---")
        self.pandas_query_engine = PandasEngine(self.config).build()

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
        # 兼容旧名称与工具名称
        if source in ("notion", "notion_knowledge_base"):
            return self.notion_query_engine
        if source in ("local", "document_analyzer"):
            return self.rag_query_engine
        if source in ("pandas", "sales_data_analyzer"):
            return self.pandas_query_engine
        return None
