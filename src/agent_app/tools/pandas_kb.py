import os
from typing import Optional

from langchain_core.tools import tool
from dotenv import load_dotenv

from pathlib import Path
import sys

# 懒加载 RAGSystem，避免循环导入
ROOT = Path(__file__).resolve().parents[2]
src_path = ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
from rag.system import RAGSystem, RAGConfig  # noqa: E402


load_dotenv()

_rag: Optional[RAGSystem] = None


def _init_rag_impl() -> str:
    global _rag
    cfg = RAGConfig()
    # 允许通过环境变量覆盖 CSV 路径
    if os.getenv("CSV_FILE_PATH"):
        cfg.CSV_FILE_PATH = os.getenv("CSV_FILE_PATH")  # type: ignore
    if os.getenv("CSV_DIR_PATH"):
        cfg.CSV_DIR_PATH = os.getenv("CSV_DIR_PATH")  # type: ignore
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


