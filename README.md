# 奇点AI Agent

一体化对话与任务代理：默认走简单聊天；在命理模式与深度思考模式下，按需启用受限域智能路由与 ReAct 工具链，支持流式输出与可扩展的 RAG 能力。

## 目录
- 项目概述
- 核心能力
- 快速开始
- 运行与模式说明
- API 速览
- 部署与持久化

## 项目概述
- 名称：奇点AI Agent
- 一句话：简单问题直答，复杂任务智能分流（命理/研究/RAG），前后端一体化、流式反馈。
- 主要价值：
  - 默认直连 LLM，响应快、成本低；
  - 按按钮选择“命理/深度思考”时，自动切换到合适的 Agent 与工具；
  - 支持本地与云端向量库，便于生产部署与数据持久化。

## 核心能力
- 简单聊天直答：`default_llm_agent`，无 ReAct、稳定输出。
- 命理智能分析：命理模式下受限域智能路由，命理问题走 `fortune_agent`，非命理回退聊天。
- 深度思考检索：深度模式下在 `research_agent` 与 `general_rag_agent` 之间路由，支持网络检索与本地/Pandas 知识库。
- 流式输出：`/query_stream` 持续返回增量文本，前端顺滑展示。
- 用户级会话：历史消息、会话标题、搜索、重命名、删除和刷新恢复由 Go 与
  PostgreSQL 持久化。

## 快速开始

推荐使用开发 Compose，一次启动带热更新的前端、Go 网关、Python Agent、
PostgreSQL 和 Redis：

```bash
docker compose -f docker-compose.dev.yml up --build
```

访问 `http://localhost:5173`，先注册本地账户再进入聊天页。前端代码由
Vite 热更新，日常修改不需要重新构建镜像；只有依赖、Dockerfile 或生产镜像
内容变化时才需要重新构建。

也可以手动启动各服务：

1) 安装依赖（建议 Python 3.11+）
```bash
pip install -r backend/requirements.txt
```
2) 本地运行 Python Legacy API
```bash
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```
3) 本地运行 Go 公网入口
```bash
cd go-backend
go run ./cmd/server
```

启动 Go 前设置 `HTTP_ADDR=:8000` 和
`PYTHON_BASE_URL=http://127.0.0.1:8001`。

4) 本地运行前端
```bash
cd frontend
npm install
npm run dev
```

> 环境变量：复制根目录 `.env.example` 为根目录 `.env`。本地 Python 与
> Docker Compose 统一读取这一份配置；至少设置 `DASHSCOPE_API_KEY`、
> `POSTGRES_PASSWORD`，并生成至少 32 字符的 `INTERNAL_AGENT_SECRET`。

## 运行与模式说明
前端通过按钮提供模式提示，后端仍会执行意图分类：
- 默认/未选：全局智能路由
- `fortune` 或 `fortune_agent`：命理智能路由
  - 真命理 → `fortune_agent`
  - 闲聊/非命理 → 回退 `default_llm_agent`
- `research` 或 `research_agent`：深度思考智能路由
  - 研究/检索 → `research_agent`
  - 一般分析 → `general_rag_agent`
  - 闲聊 → 回退 `default_llm_agent`
- `general_rag_agent` 和 `default_llm_agent` 当前不会被公网 Handler 强制路由，
  会按自动模式处理

公网流最终只有 `default`、`research`、`fortune` 三条执行路径。当前 RAG
节点全局停用，本地 KB/Pandas 不在 `/query_stream` 的实际执行链中。

## API 速览
- POST `/api/v1/auth/register`：注册并建立登录 Session
- POST `/api/v1/auth/login`：登录并建立登录 Session
- GET `/api/v1/session`：恢复当前 Session
- GET `/api/v1/me`：读取当前用户
- POST `/api/v1/auth/logout`：注销当前 Session
- GET/POST `/api/v1/conversations`：查询或创建当前用户会话
- GET/PATCH/DELETE `/api/v1/conversations/{id}`：读取、重命名或删除会话
- GET `/api/v1/conversations/{id}/messages`：分页读取历史消息
- POST `/api/v1/conversations/{id}/messages/stream`
  - 入参：`{ content, client_message_id, agent_name? }`
  - Go 从数据库组装可信历史，并持久化完成、停止或失败状态
  - SSE 首帧返回会话、消息和运行 ID
- POST `/query_stream`
  - 旧版兼容入口，暂不移除
  - 入参：`{ query: string, agent_name?: string, chat_history?: {role,content}[] }`
  - SSE 流式返回：`data: {"type":"delta","data":"..."}`，结束为
    `data: {"type":"done"}`
  - 需要 Session Cookie 和会话接口返回的 `X-CSRF-Token`
- GET `/healthz`：Go 网关进程健康
- GET `/readyz`：Go 网关与 Python 上游均可用

## 部署与持久化
- 生产部署：`docker compose up --build -d`
- Go 是唯一公网入口；Python Agent、PostgreSQL 和 Redis 只在内部网络开放。
- 当前 Go 负责认证、会话与流式运行生命周期，但尚未直接执行 Python Tool。默认
  Agent 与工具会在后续阶段逐项迁移。
- 用户、登录身份、服务端 Session、会话、消息和 Agent 运行记录均由 Go
  写入 PostgreSQL。
- 数据持久化（RAG）：
  - 开发：默认使用本地 Chroma（`backend/storage/chroma`）
  - 生产：配置 `DATABASE_URL` 与 `ENVIRONMENT=production`，自动切换到 PostgreSQL（pgvector）。
  - 提供 `backend/scripts/migrate_chroma_to_pg.py` 用于数据迁移。

---
更多细节请参考 `DEPLOYMENT.md` 与源码注释。
