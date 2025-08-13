import os
from typing import Optional

from langchain_core.tools import tool
from src.core.settings import settings

from src.rag.system import RAGSystem, RAGConfig  # type: ignore



_rag: Optional[RAGSystem] = None


def _init_rag_impl() -> str:
    global _rag
    cfg = RAGConfig()
    # 允许通过环境变量覆盖 CSV 路径
    if settings.CSV_FILE_PATH:
        cfg.CSV_FILE_PATH = settings.CSV_FILE_PATH  # type: ignore
    if settings.CSV_DIR_PATH:
        cfg.CSV_DIR_PATH = settings.CSV_DIR_PATH  # type: ignore
    _rag = RAGSystem(cfg)
    _rag.startup()
    return "Pandas RAG 初始化完成"


@tool
def init_pandas_rag() -> str:
    """
    初始化 Pandas CSV 检索引擎。
    如果设置了环境变量 CSV_FILE_PATH 或 CSV_DIR_PATH，将按其读取 CSV。
    """
    return _init_rag_impl()


@tool
def query_pandas_data(question: str) -> str:
    """
    基于已初始化的 Pandas 引擎进行问答。
    - question: 查询问题（会生成 Python 代码对 CSV 进行分析）。
    若未初始化，将自动初始化。
    """
    global _rag
    if _rag is None:
        _init_rag_impl()
    qe = _rag.get_query_engine("pandas")
    if qe is None:
        return "错误：Pandas 引擎不可用。请检查 CSV 是否存在于 data/raw 或配置 CSV_FILE_PATH/CSV_DIR_PATH。"
    return str(qe.query(question))


