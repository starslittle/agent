"""数据库连接管理"""

from typing import Optional
from langchain_community.vectorstores.pgvector import PGVector
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from app.core.settings import settings


def get_db_connection():
    """
    获取数据库连接

    Returns:
        数据库连接对象
    """
    # TODO: 实现数据库连接逻辑
    pass


def get_vector_store(
    collection_name: str = "rag_documents",
    embedding_function: Optional[HuggingFaceBgeEmbeddings] = None,
) -> PGVector:
    """
    获取 PGVector 向量存储

    Args:
        collection_name: 集合名称
        embedding_function: 嵌入函数

    Returns:
        PGVector 实例
    """
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL 未设置，请检查环境配置")

    if embedding_function is None:
        embedding_function = HuggingFaceBgeEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            encode_kwargs={"normalize_embeddings": True},
        )

    vectordb = PGVector(
        connection_string=settings.DATABASE_URL,
        embedding_function=embedding_function,
        collection_name=collection_name,
    )

    return vectordb
