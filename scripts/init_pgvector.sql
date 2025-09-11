-- 初始化 pgvector 扩展和数据库结构
-- 这个脚本将在 PostgreSQL 容器启动时自动运行

-- 创建 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建主要的 RAG 文档表（由 langchain-community 的 PGVector 自动管理）
-- 这里只是预先准备，实际表结构会由 PGVector 类自动创建

-- 为向量搜索创建索引（可选，PGVector 会自动处理）
-- 注意：实际的表和索引会在第一次使用 PGVector 时自动创建

-- 显示扩展安装状态
SELECT 'pgvector extension installed successfully' as status;

