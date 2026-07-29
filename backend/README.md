# Python Agent Service

Python 服务是启点 Agent 的执行面。它不拥有用户、会话、消息或产品 Run
等业务事实，只负责执行 Agent、保存短期 Runtime 状态并向 Go 发布稳定事件。

## 唯一执行路径

```text
app/api/agent_runs.py（V1） ─┐
app/api/graph_routes.py（Legacy Adapter）
                             ├─> app/runtime/registry.py
                             -> app/runtime/langgraph_v1.py
                             -> agent/application.py
                             -> agent/graph.py
                             -> agent/workflows/*
                             -> ModelGateway / Capability Registry
```

`graph_routes.py` 只转换旧 SSE 协议。仓库中不再保留顶层 `graph/`、第二套 RAG
Agent、手写 `stream_graph` 或 Provider 直连节点。

## 目录职责

```text
backend/
├── app/
│   ├── api/                 # 内部 V1 API、Legacy 协议适配、HMAC
│   ├── observability/       # 脱敏与稳定 Trace/Event 投影
│   └── runtime/             # Store、lease、fencing、checkpoint、Redis 通知
├── agent/
│   ├── application.py       # Runtime 到 Root Graph 的唯一入口
│   ├── graph.py             # 唯一 Root Graph
│   ├── workflows/           # chat_v1 / research_v1 / fortune_v1
│   ├── models/              # Provider 无关 Gateway 与百炼适配
│   ├── tools/               # Tool 实现及唯一 Capability Registry
│   └── prompts/             # 受 hash/provenance 管理的 Prompt
├── configs/agents.yaml      # 唯一 AgentSpec 与策略配置
├── scripts/                 # Runtime schema/setup
└── tests/                   # 契约、单元与 PostgreSQL 故障恢复
```

## 依赖

Python 版本固定为 `>=3.11,<3.13`，`pyproject.toml + uv.lock` 是唯一依赖来源。

```powershell
uv sync --frozen --group target-test --python 3.11
```

Docker 镜像也只从这两个文件安装依赖。最终运行镜像不包含 Node/npm。

## 启动

从根目录 `.env.example` 创建本地 `.env`，或向进程注入环境变量。不要提交真实
Provider Key、数据库密码或内部签名密钥。

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

主要内部接口：

- `GET /internal/health`
- `GET /internal/ready`
- `GET /internal/v1/capabilities`
- `POST /internal/v1/agent-runs:stream`
- `GET /internal/v1/agent-runs/{execution_id}`
- `DELETE /internal/v1/agent-runs/{execution_id}`
- `POST /query_stream`（Legacy 协议适配）

除健康与能力清单外，内部接口要求 Go 生成 HMAC v1 签名。生产环境不得把 Python
直接暴露到公网。

## Runtime 模式

本地轻量模式：

```dotenv
AGENT_RUNTIME_STORE=memory
AGENT_RUNTIME_COORDINATION=none
```

持久/多副本目标模式：

```dotenv
AGENT_RUNTIME_STORE=postgres
AGENT_RUNTIME_COORDINATION=redis
AGENT_RUNTIME_CHECKPOINT_SETUP=false
```

PostgreSQL 保存 execution、短期 Event Outbox、Artifact staging、lease/fencing 与
LangGraph checkpoint。Redis 只降低通知和取消延迟；Redis 故障时继续用 PostgreSQL
轮询，绝不把 Redis 当作运行事实源。

生产建表必须作为独立部署步骤执行：

```powershell
uv run python scripts/setup_agent_runtime.py
```

不要在生产请求进程中设置 `AGENT_RUNTIME_CHECKPOINT_SETUP=true`。

## 添加能力或工作流

能力必须在 `agent/tools/registry.py` 登记版本、输入输出 schema、effect、
idempotent、shadow 权限、deadline 与资源限制。AgentSpec 白名单必须与 Registry
一致。当前迁移只启用只读且幂等的能力；非幂等写能力在 durable operation ledger
落地前会被 readiness 拒绝。

新 Workflow 必须：

1. 作为 `agent/workflows/` 下的独立 Subgraph；
2. 通过 `AgentApplication` 与 Root Graph 进入；
3. 只调用 Model Gateway 与 Capability Executor；
4. 使用 RunContext 的 deadline、取消和预算；
5. 产生稳定事件与 Artifact，而不是写 Go 的业务表；
6. 提供 Fake Model/Fake Capability 契约测试。

## 验证

```powershell
uv lock --check
uv run pytest tests/unit -q
uvx ruff check agent app tests scripts
```

真实 PostgreSQL 集成测试需要显式设置 `TEST_DATABASE_URL`，默认不会
接触真实数据库。完整审核与回滚步骤见
[`docs/operations/agent-runtime-rollout.md`](../docs/operations/agent-runtime-rollout.md)。
