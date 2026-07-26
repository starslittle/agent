# QidianAgent Backend

## 项目结构

本项目采用分层架构设计，遵循领域驱动设计（DDD）原则。

```
backend/
├── app/                     # 内部 Agent API、Runtime 与服务启动
├── graph/                   # LangGraph 图与节点
├── agent/                   # 智能体能力层（工具注册表/Worker/提示词）
├── rag/                     # RAG 体系（引擎/检索器/管线）
├── infra/                   # 基础设施（数据库/缓存/存储/日志）
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

本地直接运行 Python 时，在 `backend` 目录创建独立的 `.env`：

```bash
cp ../.env.example .env
```

主要配置项：
- `DASHSCOPE_API_KEY`: 通义千问 API 密钥
- `TAVILY_API_KEY`: Tavily 搜索密钥（可选）
- `SENIVERSE_API_KEY`: 心知天气密钥（可选）
- `INTERNAL_AGENT_SECRET`: 与 Go 网关一致的内部 HMAC 密钥
- `AGENT_SERVICE_VERSION`: Agent Service 发布版本
- `PORT`: 服务端口（默认 8000）

Python Agent Service 不负责用户、会话、消息或 Run 的业务数据写入；这些数据
只由 Go 网关写入 PostgreSQL。

### 3. 启动服务

```bash
uvicorn app.main:app --reload --port 8000
```

也可以完全以 `backend` 为构建上下文：

```bash
docker build -t qidian-python-agent .
```

### 4. 内部接口

- 健康检查: `GET /internal/health`
- 能力清单: `GET /internal/v1/capabilities`
- 开始/续接执行: `POST /internal/v1/agent-runs:stream`
- 执行状态: `GET /internal/v1/agent-runs/{execution_id}`
- 幂等取消: `DELETE /internal/v1/agent-runs/{execution_id}`
- Legacy 回滚入口: `POST /query_stream`

除健康检查与能力清单外，内部接口要求 Go 生成的 HMAC v1 签名。生产部署只应
通过内部网络暴露 Python 服务。

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

1. 在 `agent/tools/` 创建工具实现
2. 在 `agent/tools/registry.py` 注册唯一名称、用途、副作用、幂等性、影子权限、
   超时、输入输出上限和并发类型
3. 阻塞、高内存或不可协作取消的实现使用 `process`，由可终止 Heavy Worker
   隔离执行
4. 为能力清单、影子限制、超时与取消补充契约测试

### 添加新的 RAG 管线

1. 在 `rag/pipelines/` 创建管线文件
2. 在 `rag/pipelines/__init__.py` 中导出
3. 在 `configs/rag.yaml` 中配置

### 运行测试

```bash
# 快速协议、Runtime、签名和工具回归集
pytest tests/unit -q
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
postgresql://<user>:<password>@<host>:<port>/<database>?client_encoding=utf8
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
