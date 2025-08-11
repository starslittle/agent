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


def _init_rag_impl(force: bool = False, refresh: bool = False) -> str:
    global _rag
    cfg = RAGConfig()
    _rag = RAGSystem(cfg)
    if force:
        # 强制重建：清理本地向量库目录
        try:
            import shutil
            chroma_dir = getattr(cfg, "CHROMA_LOCAL_DIR", cfg.CHROMA_DB_DIR)
            shutil.rmtree(chroma_dir, ignore_errors=True)
        except Exception:
            pass
    _rag.startup()
    if refresh and not force:
        # 增量刷新
        try:
            from rag.engines.local import LocalEngine

            LocalEngine(cfg).refresh()
        except Exception:
            pass
    return "本地文档 RAG 初始化完成"


@tool
def init_local_rag(force: bool = False, refresh: bool = False) -> str:
    """
    初始化本地文档（PDF/TXT）RAG。
    将待检索的 PDF 放到 data/raw 目录。
    - force: True 则清空并重建索引。
    - refresh: True 则在已有索引上做增量刷新（可能产生重复向量）。
    """
    # 幂等：若已初始化且未 force/refresh，则直接返回
    global _rag
    if _rag is not None and not force and not refresh:
        return "本地文档 RAG 已初始化"
    return _init_rag_impl(force=force, refresh=refresh)


@tool
def query_local_kb(question: str, top_k: int = 3) -> str:
    """
    基于已初始化的本地文档索引进行问答。
    - question: 查询问题。
    - top_k: 相似检索返回条数（默认 3）。
    若未初始化，将自动初始化。
    """
    global _rag
    if _rag is None:
        # 未初始化时按默认不强制、不刷新地初始化一次
        _init_rag_impl()
    qe = _rag.get_query_engine("local")
    if qe is None:
        return "错误：本地文档引擎不可用。请确认 data/raw 中存在 PDF/TXT 文件并重新初始化。"
    try:
        qe._similarity_top_k = top_k
    except Exception:
        pass
    try:
        return str(qe.query(question))
    except Exception as e:
        return (
            "错误：本地 RAG 回答阶段调用 LLM 失败，可能为网络/证书/代理问题。"
            f" 详细：{e}"
        )


