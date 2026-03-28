# QidianAgent Backend

## 项目结构

本项目采用分层架构设计，遵循领域驱动设计（DDD）原则。

```
backend/
├── app/                     # 应用层（API/服务启动/路由）
├── graph/                   # LangGraph 图与节点
├── agent/                   # 智能体能力层（工具/提示词/策略）
├── rag/                     # RAG 体系（引擎/检索器/管线）
├── infra/                   # 基础设施（数据库/缓存/存储/日志）
├── workers/                 # 异步/批处理任务
├── configs/                 # 配置文件
├── scripts/                 # 运维/迁移脚本
├── tests/                   # 单测/集成测试
└── requirements/            # 依赖拆分
```

## 快速开始

### 1. 安装依赖

```bash
# 安装基础依赖
pip install -r requirements/base.txt

# 安装 API 依赖
pip install -r requirements/api.txt

# 安装数据库依赖
pip install -r requirements/database.txt

# 安装缓存依赖
pip install -r requirements/cache.txt

# 安装 Agent 依赖
pip install -r requirements/agent.txt

# 开发环境
pip install -r requirements/dev.txt
```

### 2. 配置环境变量

复制并编辑 `.env` 文件：

```bash
cp .env.example .env
```

主要配置项：
- `DASHSCOPE_API_KEY`: 通义千问 API 密钥
- `DATABASE_URL`: PostgreSQL 数据库连接字符串
- `REDIS_URL`: Redis 连接字符串（可选）
- `PORT`: 服务端口（默认 8002）

### 3. 启动服务

```bash
# 方式1：使用 run.py
python run.py

# 方式2：使用 uvicorn
uvicorn app.main:app --reload --port 8002
```

### 4. 访问服务

- API 文档: http://localhost:8002/docs
- 健康检查: http://localhost:8002/healthz

## 核心模块说明

### 应用层 (app/)

FastAPI 应用的入口层，负责：
- API 路由定义
- 请求/响应模型
- 依赖注入
- 中间件配置

### Graph 层 (graph/)

LangGraph 工作流层，负责：
- 意图路由
- 检索节点
- 工具调用节点
- 答案生成节点
- 状态管理

### Agent 层 (agent/)

智能体能力层，负责：
- 工具实现（日期、天气、搜索等）
- 提示词管理
- 路由策略

### RAG 层 (rag/)

检索增强生成层，负责：
- 向量检索引擎
- 混合检索器
- RAG 管线
- 文档处理

### Infra 层 (infra/)

基础设施层，负责：
- 数据库连接管理
- Redis 缓存
- 本地存储管理
- 日志配置

## 开发指南

### 添加新工具

1. 在 `agent/tools/` 创建工具文件
2. 在 `agent/tools/__init__.py` 中导出
3. 在 `configs/agents.yaml` 中配置

### 添加新的 RAG 管线

1. 在 `rag/pipelines/` 创建管线文件
2. 在 `rag/pipelines/__init__.py` 中导出
3. 在 `configs/rag.yaml` 中配置

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/api/
pytest tests/agents/
pytest tests/rag/

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/
```

## 配置文件

### agents.yaml

定义各种 Agent 的配置：
- LLM 模型
- 工具列表
- 提示词模板
- 执行参数

### rag.yaml

定义 RAG 系统配置：
- 向量存储配置
- 检索参数
- 重排配置

## 脚本说明

- `scripts/init_pgvector.sql`: 初始化 PostgreSQL 向量扩展
- `scripts/migrate_chroma_to_pg.py`: 从 Chroma 迁移到 PGVector
- `scripts/run_ragas_eval.py`: 运行 RAG 评估

## 迁移说明

如果你正在从旧结构迁移，请参考：
- [MIGRATION_GUIDE.md](./MIGRATION_SUMMARY.md): 详细的迁移指南
- [MIGRATION_SUMMARY.md](./MIGRATION_SUMMARY.md): 迁移完成总结

## 常见问题

### 1. 导入错误

确保 backend 目录在 Python 路径中：
```python
import sys
from pathlib import Path
backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))
```

### 2. 数据库连接失败

检查 `DATABASE_URL` 格式：
```
postgresql://username:password@host:port/database?client_encoding=utf8
```

### 3. Redis 连接失败

确保 Redis 服务运行，并检查 `REDIS_URL` 配置。

## 技术栈

- **框架**: FastAPI
- **LLM**: 通义千问 (DashScope)
- **RAG**: LangChain + LlamaIndex
- **向量数据库**: PGVector
- **缓存**: Redis
- **数据库**: PostgreSQL
- **工作流**: LangGraph（待集成）

## 许可证

MIT License

## 联系方式

如有问题，请提交 Issue。
