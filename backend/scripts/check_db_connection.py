import os
import sys
from pathlib import Path

# 将后端根目录添加到 Python 路径，以便导入 settings
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

try:
    # 尝试导入 psycopg2，这是第一道关卡
    import psycopg2
    from app.core.settings import settings
except ImportError as e:
    print(f"❌ 依赖导入失败: {e}")
    print("请确保你已在正确的 Python 环境中安装了 'psycopg2-binary'。")
    sys.exit(1)


def check_connection():
    """尝试连接到 PostgreSQL 数据库并执行简单查询"""
    db_url = settings.DATABASE_URL
    if not db_url:
        print("❌ 环境变量 DATABASE_URL 未设置。请检查你的 .env 文件。")
        return

    print(f"[*] 正在尝试连接到数据库: {db_url}")

    try:
        # 尝试建立连接
        conn = psycopg2.connect(db_url)
        print("✅ 数据库连接成功！")

        # 使用 cursor 执行一个简单的查询
        cursor = conn.cursor()

        # 检查 pgvector 扩展
        print("[*] 正在检查 pgvector 扩展...")
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        result = cursor.fetchone()
        if result:
            print("✅ pgvector 扩展已成功安装。")
        else:
            print("❌ pgvector 扩展未找到。请检查 'scripts/init_pgvector.sql' 是否正确执行。")

        # 检查 langchain 表
        print("[*] 正在检查 LangChain 表...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name IN ('langchain_pg_collection', 'langchain_pg_embedding');
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if 'langchain_pg_collection' in tables:
            print("✅ 'langchain_pg_collection' 表存在。")
        else:
            print("⚠️ 'langchain_pg_collection' 表不存在。这通常意味着数据摄取尚未运行或失败。")

        if 'langchain_pg_embedding' in tables:
            print("✅ 'langchain_pg_embedding' 表存在。")
        else:
            print("⚠️ 'langchain_pg_embedding' 表不存在。这通常意味着数据摄取尚未运行或失败。")

        # 关闭连接
        cursor.close()
        conn.close()

    except psycopg2.OperationalError as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 数据库连接失败: {e}")
        print("\n请检查以下几点：")
        print("  1. PostgreSQL Docker 容器是否正在运行？ (运行 `docker-compose ps`)")
        print("  2. DATABASE_URL 中的主机名、端口、用户名和密码是否正确？")
        print("  3. 防火墙是否阻止了到端口 5432 的连接？")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 发生未知错误: {e}")


if __name__ == "__main__":
    check_connection()

