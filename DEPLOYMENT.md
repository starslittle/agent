# 部署指南

## 拓扑与边界

```text
Internet
   -> Go Gateway :8000
      -> Python Agent Service :8000（内部）
      -> PostgreSQL（内部）
      -> Redis（内部）
```

Go 是唯一公网入口，拥有认证、会话、消息和产品 Run。Python 运行唯一的
LangGraph Agent Application，并只写 `agent_runtime` schema。Redis 只用于通知，
PostgreSQL 是运行与回放事实源。

不要发布 Python、PostgreSQL、Redis 或开发 Adminer 到公网。

## 配置

```powershell
Copy-Item .env.example .env
```

至少通过 Secret 管理系统提供：

- `DASHSCOPE_API_KEY`
- `POSTGRES_PASSWORD`
- `INTERNAL_AGENT_SECRET`（至少 32 字符，Go/Python 相同）
- 生产 HTTPS `PUBLIC_ORIGINS`
- Research 需要的 `TAVILY_API_KEY`

不要把真实值写入镜像、Compose、日志或 Git。进入过 Git 历史的凭据必须在外部平台
撤销并轮换。

## 开发

```powershell
.\start.bat
```

默认使用宿主机 Vite 连接 Docker Gateway：脚本会读取 `.env` 中的 `PORT`，停止可能
占用 `5173` 的 Docker 前端，只在 Docker 中启动 Gateway 及其 Python、PostgreSQL、
Redis 依赖，然后在宿主机启动前端。前端请求仍通过 Vite Proxy 进入 Go，浏览器不
直连 Python。

容器化前端保留为回退方式：

```powershell
docker compose -f docker-compose.dev.yml up -d --wait frontend
```

- 前端：`http://localhost:5173`
- Go：`http://localhost:<.env 中的 PORT>`，默认 `8000`
- Adminer：`http://127.0.0.1:8082`

Adminer 必须选择 `PostgreSQL`，服务器为 `postgres`。它只在开发 Compose 中存在，
并且仅监听本机。

## 生产构建

```powershell
docker compose --env-file .env -f docker-compose.yml config --quiet
docker compose build
```

生产 Compose 有意默认：

```dotenv
AGENT_PROTOCOL_MODE=legacy
AGENT_RUNTIME_STORE=memory
AGENT_RUNTIME_COORDINATION=none
```

这不是最终性能配置，而是人工上线门禁。数据库 migration、checkpoint setup、
最小权限、分阶段切换和回滚必须按
[`docs/operations/agent-runtime-rollout.md`](docs/operations/agent-runtime-rollout.md)
执行。

完成审核后才逐步切换：

```dotenv
AGENT_PROTOCOL_MODE=v1
AGENT_RUNTIME_STORE=postgres
AGENT_RUNTIME_COORDINATION=redis
AGENT_RUNTIME_CHECKPOINT_SETUP=false
```

## 启动与健康

```powershell
docker compose up -d
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
```

- `/healthz`：Go 进程存活；
- `/readyz`：Go 数据库与 Python 上游可用；
- Python `/internal/ready`：AgentSpec、Root Graph、Runtime Store、Checkpoint、模型
  配置与协调后端就绪。

查看日志：

```powershell
docker compose ps
docker compose logs -f gateway python
```

停止时不要随意使用 `down -v`，它会删除数据库卷。

## 镜像

- `go-backend/Dockerfile`：Go 网关、一次性 `qidian-migrate` 和前端产物；
- `backend/Dockerfile`：Python 3.11 Agent Runtime；
- `pyproject.toml + uv.lock`：唯一 Python 依赖来源。

Python 最终镜像不包含 Node/npm。Node 只在 builder 阶段满足个别包的构建需求。

## 回滚原则

- V1 传输异常：先切回 `AGENT_PROTOCOL_MODE=legacy`；
- Redis 异常：切回 `AGENT_RUNTIME_COORDINATION=none`；
- PostgreSQL Runtime 回退到 memory 前必须停止新流量并收口活跃 Run；
- Agent 行为异常：回滚到预先记录的上一稳定镜像 digest；
- 事故中不要删除 `agent_runtime` schema，也不要把浏览器直连 Python。

完整回滚顺序和人工批准清单见上线手册。
