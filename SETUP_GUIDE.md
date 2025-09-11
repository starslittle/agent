# 八字功能集成设置指南

## 环境准备

### 1. 配置环境变量
复制 `env.example` 为 `.env` 并配置必要的变量：
```bash
cp env.example .env
```

确保 `.env` 文件中包含以下配置：
```bash
# 必须配置
DASHSCOPE_API_KEY=your_dashscope_api_key_here
DATABASE_URL=postgresql://agent_user:agent_password@localhost:5432/agent_db
ENVIRONMENT=development
```

### 2. 启动 PostgreSQL 数据库
```bash
# 启动数据库和相关服务
docker-compose up -d postgres redis

# 查看服务状态
docker-compose ps
```

### 3. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

## 数据摄取步骤

### 选项1：摄取所有类型的文档
```bash
python -m src.workers.ingest_documents --all --rebuild
```

### 选项2：分别摄取不同类型
```bash
# 摄取八字文档
python -m src.workers.ingest_documents --source-type bazi --rebuild

# 摄取紫微文档  
python -m src.workers.ingest_documents --source-type ziwei --rebuild

# 摄取通用命理文档
python -m src.workers.ingest_documents --source-type fortune --rebuild
```

## 验证摄取结果

摄取完成后，你可以通过以下方式验证：

1. **检查数据库**：
   ```sql
   -- 连接到数据库
   psql postgresql://agent_user:agent_password@localhost:5432/agent_db
   
   -- 查看摄取的文档数量
   SELECT 
       metadata->>'source_type' as source_type,
       COUNT(*) as document_count
   FROM langchain_pg_embedding 
   WHERE collection_id IN (
       SELECT uuid FROM langchain_pg_collection 
       WHERE name = 'rag_documents'
   )
   GROUP BY metadata->>'source_type';
   ```

2. **启动应用测试**：
   ```bash
   docker-compose up -d
   # 或直接运行
   python -m src.api.main
   ```

## 故障排除

### 常见问题：

1. **数据库连接失败**
   - 确保 PostgreSQL 容器正在运行
   - 检查 `DATABASE_URL` 配置是否正确

2. **PDF 处理失败**
   - 确保安装了 PDF 处理库：`pip install PyPDF2 pdfplumber pymupdf`

3. **DOCX 处理失败**
   - 确保安装了 DOCX 处理库：`pip install python-docx docx2txt`

4. **摄取脚本找不到文件**
   - 检查文件是否放在正确的目录：
     - 八字：`data/raw/bazi/`
     - 紫微：`data/raw/ziwei/`
     - 通用：`data/raw/`（排除 bazi 和 ziwei 子目录）

