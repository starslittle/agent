import logging
from pathlib import Path
from typing import List, Optional

import chromadb
import requests
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
try:
    from llama_index.postprocessor import SentenceTransformerRerank
except Exception:
    SentenceTransformerRerank = None  # type: ignore

try:
    from llama_index.readers.notion import NotionPageReader, NotionDatabaseReader  # type: ignore
    HAS_DB_READER = True
except Exception:
    from llama_index.readers.notion import NotionPageReader  # type: ignore
    NotionDatabaseReader = None  # type: ignore
    HAS_DB_READER = False


logger = logging.getLogger(__name__)


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


class NotionEngine:
    name = "notion"
    tool_name = "notion_knowledge_base"
    description = "Notion 工作区知识库检索与问答。"

    def __init__(self, config):
        self.config = config

    def build(self) -> Optional[BaseQueryEngine]:
        if not getattr(self.config, "ENABLE_NOTION", False):
            logger.info("未启用 Notion 集成，跳过构建 Notion 引擎。")
            return None
        if not getattr(self.config, "NOTION_API_KEY", ""):
            logger.warning("未设置 NOTION_API_KEY，跳过 Notion 引擎构建。")
            return None
        try:
            # 将 Notion 向量库存放到独立子目录
            chroma_dir = getattr(self.config, "CHROMA_NOTION_DIR", self.config.CHROMA_DB_DIR)
            chroma_client = chromadb.PersistentClient(path=chroma_dir)
            chroma_collection = chroma_client.get_or_create_collection(self.config.NOTION_COLLECTION_NAME)
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            index: Optional[VectorStoreIndex] = None
            if chroma_collection.count() > 0 and Path(chroma_dir).exists():
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
                        documents.extend(
                            db_reader.load_data(database_id=_format_uuid_with_hyphens(self.config.NOTION_DATABASE_ID)) or []
                        )
                    else:
                        page_ids = _fetch_page_ids_from_database(
                            self.config.NOTION_API_KEY, self.config.NOTION_DATABASE_ID
                        )
                        if page_ids:
                            page_reader = NotionPageReader(integration_token=self.config.NOTION_API_KEY)
                            documents.extend(page_reader.load_data(page_ids=page_ids) or [])
                        else:
                            logger.warning("无法通过数据库ID获取页面列表，可能是权限/ID 无效或数据库为空。")
                if not documents:
                    logger.warning("未从 Notion 拉取到任何文档，跳过 Notion 引擎创建。")
                    return None
                nodes = SentenceSplitter().get_nodes_from_documents(documents)
                index = VectorStoreIndex(nodes, storage_context=storage_context, show_progress=True)

            if index:
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
            logger.error(f"构建 Notion 引擎时出错: {e}", exc_info=True)
            return None


