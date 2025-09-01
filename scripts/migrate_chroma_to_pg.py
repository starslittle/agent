#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据迁移脚本：将本地 ChromaDB 的向量数据迁移到云端 PostgreSQL (PGVector)

使用方法:
1. 确保在 .env 文件中设置了 DATABASE_URL（云端 PostgreSQL 的外部连接 URL）
2. 在项目根目录运行: python scripts/migrate_chroma_to_pg.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_community.vectorstores.pgvector import PGVector
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_core.documents import Document

# 添加项目根目录到 Python 路径，以便导入 src 模块
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.settings import settings

# --- 配置部分 ---
# 旧 ChromaDB 的路径和集合名称（请根据你的 agents.yaml 配置修改）
OLD_CHROMA_PATH = "./storage/chroma/local"
COLLECTION_NAME = "local"
# --- 配置结束 ---


def run_migration():
    """
    将本地 ChromaDB 的数据迁移到云端 PostgreSQL (PGVector)。
    """
    print("=" * 60)
    print("开始数据迁移：ChromaDB → PostgreSQL (PGVector)")
    print("=" * 60)
    
    # 1. 加载环境变量
    load_dotenv()

    # 2. 检查 DATABASE_URL 是否已设置
    db_url = settings.DATABASE_URL
    if not db_url:
        print("❌ 错误: 请在 .env 文件中设置 DATABASE_URL")
        print("   示例: DATABASE_URL=postgres://user:password@host:port/database")
        return False

    print(f"✅ 数据库连接 URL 已配置")

    # 3. 初始化 Embedding 模型
    print("📦 正在加载 Embedding 模型...")
    embeddings = HuggingFaceBgeEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        encode_kwargs={"normalize_embeddings": True},
    )
    print("✅ Embedding 模型加载完成")

    # 4. 连接到旧的本地 ChromaDB
    print(f"🔍 正在连接到本地 ChromaDB: {OLD_CHROMA_PATH}")
    chroma_path = Path(OLD_CHROMA_PATH)
    if not chroma_path.exists():
        print(f"❌ 错误: 找不到 ChromaDB 路径 '{OLD_CHROMA_PATH}'")
        print("   请确认路径是否正确，或者 ChromaDB 是否已初始化")
        return False
        
    try:
        old_db = Chroma(
            persist_directory=str(chroma_path),
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME,
        )
        print("✅ 成功连接到本地 ChromaDB")
    except Exception as e:
        print(f"❌ 连接 ChromaDB 失败: {e}")
        return False

    # 5. 获取所有文档
    print("📄 正在从 ChromaDB 获取所有文档...")
    try:
        # .get() 会返回文档内容和元数据
        results = old_db.get(include=["metadatas", "documents"])
        docs_content = results.get("documents", [])
        docs_metadata = results.get("metadatas", [])
        
        if not docs_content:
            print("⚠️  ChromaDB 中没有找到任何文档。迁移结束。")
            return True
            
        print(f"✅ 共找到 {len(docs_content)} 篇文档需要迁移")
        
        # 将文档内容和元数据组合成 Document 对象
        documents = []
        for i, content in enumerate(docs_content):
            metadata = docs_metadata[i] if i < len(docs_metadata) else {}
            documents.append(Document(page_content=content, metadata=metadata))
            
    except Exception as e:
        print(f"❌ 获取 ChromaDB 文档失败: {e}")
        return False

    # 6. 连接到新的 PostgreSQL 数据库并写入数据
    print(f"🚀 正在连接到 PostgreSQL 并写入数据到集合 '{COLLECTION_NAME}'...")
    
    try:
        # PGVector.from_documents 会自动创建表和扩展（如果不存在）
        # 并将所有文档一次性添加进去
        new_db = PGVector.from_documents(
            documents=documents,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            connection_string=db_url,
            # 第一次创建时需要预删除，确保表是干净的
            pre_delete_collection=True, 
        )
        print("✅ 数据写入 PostgreSQL 成功")
        
    except Exception as e:
        print(f"❌ 写入 PostgreSQL 失败: {e}")
        print("   请检查数据库连接 URL 是否正确，以及数据库是否支持 pgvector 扩展")
        return False

    # 7. 验证迁移结果
    print("🔍 正在验证迁移结果...")
    try:
        # 尝试进行一次搜索来验证数据是否正确迁移
        test_results = new_db.similarity_search("测试", k=1)
        print(f"✅ 验证成功：能够从 PostgreSQL 中检索到 {len(test_results)} 个结果")
    except Exception as e:
        print(f"⚠️  验证警告: {e}")
        print("   数据可能已迁移，但搜索功能可能需要调试")

    print("\n" + "=" * 60)
    print("🎉 数据迁移成功完成！")
    print(f"📊 统计: {len(documents)} 篇文档已成功迁移到 PostgreSQL 数据库")
    print("💡 下一步:")
    print("   1. 在生产环境的环境变量中设置 ENVIRONMENT=production")
    print("   2. 在生产环境的环境变量中设置 DATABASE_URL（使用内部连接 URL）")
    print("   3. 重新部署应用")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
