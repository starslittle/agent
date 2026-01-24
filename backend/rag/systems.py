import os
import sys
import logging
from pathlib import Path
from typing import List, Optional

import chromadb
import pandas as pd

from llama_index.core import Settings
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# 新增：引擎模块
from .engines.local import LocalEngine
from .engines.pandas_engine import PandasEngine


# 基础路径（项目根）
BASE_DIR = Path(__file__).resolve().parents[2]

from app.core.settings import settings

# 动态导入（兼容不同版本）
SimpleDirectoryReader = None
ReaderConfig = None
UnstructuredReader = None

try:
    from llama_index.core.readers import SimpleDirectoryReader  # type: ignore
    from llama_index.core.readers.file import ReaderConfig  # type: ignore
    from llama_index.core.readers.unstructured import UnstructuredReader  # type: ignore
except ImportError as e:
    logging.warning(f"部分 llama_index 导入失败: {e}")
    # 尝试其他导入路径
    try:
        from llama_index import SimpleDirectoryReader  # type: ignore
    except ImportError:
        SimpleDirectoryReader = None

    try:
        from llama_index.readers.unstructured import UnstructuredReader  # type: ignore
    except ImportError:
        UnstructuredReader = None


class RAGConfig:
    # API 和模型配置
    DASHSCOPE_API_KEY: str = settings.DASHSCOPE_API_KEY
    LLM_MODEL_NAME: str = "qwen-turbo-2025-04-28"
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
    LOCAL_COLLECTION_NAME: str = "local"
    # 允许通过环境变量 CSV_FILE_PATH 指定 CSV 路径；默认指向 data/raw 目录
    CSV_FILE_PATH: str = settings.CSV_FILE_PATH or str(BASE_DIR / "data" / "sales_data.csv")
    CSV_DIR_PATH: str = settings.CSV_DIR_PATH or str(BASE_DIR / "data" / "raw")

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGSystem:
    def __init__(self, config: RAGConfig):
        self.config = config
        self._setup_settings()
        self.rag_query_engine: Optional[BaseQueryEngine] = None
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
        self._build_pandas_engine()
        self._setup_tools()

    def get_query_engine(self, source: str = "local") -> Optional[BaseQueryEngine]:
        source = (source or "local").lower()
        # 兼容旧名称与工具名称
        if source in ("local", "document_analyzer"):
            return self.rag_query_engine
        if source in ("pandas", "sales_data_analyzer"):
            return self.pandas_query_engine
        return None
