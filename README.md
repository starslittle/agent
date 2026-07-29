# 启点 Agent

启点 Agent 是一个以 Go 为产品控制面、以 Python/LangGraph 为 Agent
执行面的对话产品。当前产品提供 Chat、Research 与 Fortune 三类工作流；长期目标是
帮助用户建立可确认、可修正、可遗忘的个人认知镜像，并支持选择推演与结果复盘。

## 架构

```text
Browser
  -> Go Gateway（认证、会话、消息、产品 Run、事件投影）
  -> Python Agent Service（Runtime、LangGraph、模型与能力）
  -> PostgreSQL（业务事实 + agent_runtime）
  -> Redis（Runtime 通知；PostgreSQL 仍是事实源）
```

Python 内部只有一条执行链：

```text
Legacy Adapter / V1 API
  -> ExecutionRegistry
  -> LangGraphV1Runtime
  -> AgentApplication
  -> Root Graph
  -> chat_v1 / research_v1 / fortune_v1
  -> ModelGateway / Capability Registry
```

Legacy 入口只负责协议兼容，不包含第二套 Graph、模型或工具执行逻辑。

关键文档：

- [产品定位](docs/product/positioning.md)
- [Agent Runtime 架构](docs/architecture/agent-runtime.md)
- [迁移状态与验收结果](docs/architecture/agent-runtime-migration-progress.md)
- [上线、回滚与人工审核](docs/operations/agent-runtime-rollout.md)
- [Go/Python 历史背景](docs/architecture/go-python-migration-history.md)

## 本地开发

复制配置并填写本地值，不要提交 `.env`：

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

服务地址：

- 前端：`http://localhost:5173`
- Go 网关：`http://localhost:8000`
- Adminer：`http://127.0.0.1:8082`

Adminer 登录时必须选择 `PostgreSQL`，服务器填写 `postgres`，其余字段使用
`.env` 中的 `POSTGRES_*`。Adminer 只存在于开发 Compose，并且只监听本机。

也可以单独启动 Python：

```powershell
cd backend
uv sync --frozen --group target-test --python 3.11
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

再启动 Go：

```powershell
cd go-backend
go run ./cmd/server
```

## 运行模式

- 开发 Compose 默认 `AGENT_PROTOCOL_MODE=v1`。
- 生产 Compose 有意默认 `AGENT_PROTOCOL_MODE=legacy`、
  `AGENT_RUNTIME_STORE=memory`、`AGENT_RUNTIME_COORDINATION=none`。
- 生产启用持久 Runtime 前，必须完成人工审核、数据库备份与 schema/grant
  步骤，再按上线文档切换为 `v1 + postgres + redis`。
- 无论 Go 使用 Legacy 还是 V1 传输，Python 都只运行 `langgraph_v1`。

浏览器断开不等于用户取消。V1 会由 Go 在后台续接并保存最终结果；只有显式停止接口
才发送语义取消。

## 主要接口

- `POST /api/v1/conversations/{id}/messages/stream`：产品流式对话入口
- `GET /api/v1/agent-runs`：运行摘要
- `GET /api/v1/agent-runs/{run_id}`：事件、Span 与 provenance
- `POST /query_stream`：Legacy 兼容入口
- `GET /healthz`、`GET /readyz`：Go 健康与就绪
- `POST /internal/v1/agent-runs:stream`：Python V1 内部入口
- `GET /healthz`：Python 进程存活
- `GET /internal/ready`：Python Graph、Store、Checkpoint 与模型配置就绪

Go 是唯一公网入口。Python、PostgreSQL 与 Redis 只应在内部网络开放。

## 验证

```powershell
cd backend
uv lock --check
uv run pytest tests/unit -q
uvx ruff check agent app tests scripts

cd ../go-backend
go test ./...
```

真实 PostgreSQL 强杀恢复演练、镜像构建及生产切换步骤见
[上线文档](docs/operations/agent-runtime-rollout.md)。
