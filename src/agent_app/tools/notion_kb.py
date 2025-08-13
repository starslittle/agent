import os
import requests
from langchain_core.tools import tool
from src.core.settings import settings
from typing import Optional

# 直接使用 namespace package 导入（uvicorn 使用 src.api.main:app 时可用）
from src.rag.system import RAGSystem, RAGConfig  # type: ignore


_rag: Optional[RAGSystem] = None


def _init_notion_rag_impl(page_ids_csv: str = "", database_id: str = "") -> str:
    global _rag
    cfg = RAGConfig()
    cfg.ENABLE_NOTION = True
    if settings.NOTION_API_KEY:
        cfg.NOTION_API_KEY = settings.NOTION_API_KEY
    if page_ids_csv:
        cfg.NOTION_PAGE_IDS = [x.strip() for x in page_ids_csv.split(",") if x.strip()]
    if database_id:
        cfg.NOTION_DATABASE_ID = database_id
    _rag = RAGSystem(cfg)
    _rag.startup()
    return "Notion RAG 初始化完成"


@tool
def init_notion_rag(page_ids_csv: str = "", database_id: str = "") -> str:
    """
    初始化 Notion RAG 索引。
    - page_ids_csv: 逗号分隔的 Notion 页面 ID 列表（可无短横线）。
    - database_id: Notion 数据库 ID（可无短横线）。
    如果两者都为空，将读取 .env 中的 NOTION_PAGE_IDS / NOTION_DATABASE_ID。
    """
    return _init_notion_rag_impl(page_ids_csv, database_id)


@tool
def query_notion_kb(question: str, top_k: int = 3) -> str:
    """
    基于已初始化的 Notion 索引进行问答。
    - question: 查询问题。
    - top_k: 相似检索返回条数（默认 3）。
    若未初始化，将自动初始化。
    """
    global _rag
    if _rag is None:
        _init_notion_rag_impl()
    qe = _rag.get_query_engine("notion")
    if qe is None:
        return "错误：Notion 引擎不可用。请先初始化。"
    try:
        qe._similarity_top_k = top_k
    except Exception:
        pass
    return str(qe.query(question))


@tool
def verify_notion_access(query: str = "", page_or_db_id: str = "") -> str:
    """
    验证 Notion 访问：可按关键词搜索或校验指定页面/数据库 ID 是否可读。
    需要在 .env 设置 NOTION_API_KEY。
    """
    notion_key = settings.NOTION_API_KEY or ""
    if not notion_key:
        return "错误：未配置 NOTION_API_KEY。"
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    out = []
    try:
        if query:
            resp = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json={"query": query, "page_size": 10},
                timeout=30,
            )
            out.append(f"search {resp.status_code}")
        if page_or_db_id:
            oid = page_or_db_id
            if "-" not in oid and len(oid) == 32:
                oid = f"{oid[0:8]}-{oid[8:12]}-{oid[12:16]}-{oid[16:20]}-{oid[20:32]}"
            rp = requests.get(f"https://api.notion.com/v1/pages/{oid}", headers=headers, timeout=20)
            rd = requests.get(f"https://api.notion.com/v1/databases/{oid}", headers=headers, timeout=20)
            out.append(f"page={rp.status_code}, db={rd.status_code}")
        return " | ".join(out) if out else "无操作"
    except Exception as e:
        return f"验证失败：{e}"
