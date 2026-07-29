# Go Gateway

Go 是启点 Agent 的公网网关和产品控制面，负责：

- 认证、Session、CSRF、限流和审计；
- 用户会话、消息与产品 Agent Run；
- 从 PostgreSQL 组装可信历史；
- 调用 Python Agent Service；
- 持久化最终回答、运行状态、关键事件、Span 与 provenance；
- V1 事件序号校验、缺口回放与失败关闭；
- 浏览器断开后的后台续接；
- 健康检查、日志、优雅退出与生产静态前端。

Go 不执行 LLM、Tool 或 LangGraph，也不写 Python 的 `agent_runtime` schema。

## 调用协议

`AGENT_PROTOCOL_MODE` 有两个传输选项：

- `v1`：版本化 Run/Event 协议，支持 execution id、幂等、重放、显式取消与恢复；
- `legacy`：回滚兼容协议。

两者最终都进入 Python 的同一个 `AgentApplication`。Legacy 不是第二套 Agent
架构。开发 Compose 默认 `v1`，生产 Compose 默认 `legacy`，待人工审核后再切换。

V1 事件必须严格连续。Go 遇到序号缺口时从最后确认序号重新附着；有限次回放仍无法
追平时以 `agent_event_sequence_gap` 失败关闭，不把部分答案标记为完整回答。

浏览器断开只是传输中断。Go 会按同一 execution id 在后台续接 Python 并保存结果；
用户显式停止才调用 Python 取消接口。

## 本地运行

先启动 PostgreSQL 和 Python Agent Service，再执行：

```powershell
cd go-backend
go run ./cmd/server
```

推荐直接使用根目录开发 Compose：

```powershell
docker compose -f docker-compose.dev.yml up --build
```

开发拓扑：

```text
Browser :5173 -> Vite -> Go :8000 -> Python :8000 (internal)
```

生产只有 Go 端口对宿主机开放。

## 关键配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `development` | 运行环境 |
| `HTTP_ADDR` | `:8080` | 监听地址 |
| `PYTHON_BASE_URL` | `http://127.0.0.1:8000` | Python 内部地址 |
| `AGENT_PROTOCOL_MODE` | `legacy` | `legacy` 或 `v1` |
| `AGENT_RUN_DEADLINE` | `5m` | 产品 Run 截止时间 |
| `AGENT_CANCEL_TIMEOUT` | `5s` | 显式取消请求时限 |
| `AGENT_RECONCILE_TIMEOUT` | `5s` | 序号缺口对账时限 |
| `GO_DATABASE_URL` | 从 `POSTGRES_*` 生成 | Go 业务数据库连接 |
| `PUBLIC_ORIGINS` | 开发本机地址 | 生产必须显式配置 |
| `COOKIE_SECURE` | 生产强制 `true` | Session Cookie |
| `SESSION_TTL` | `168h` | Session 有效期 |
| `INTERNAL_AGENT_SECRET` | 无 | Go → Python HMAC 密钥，至少 32 字符 |

## 主要 API

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/session`
- `POST /api/v1/auth/logout`
- `GET/POST /api/v1/conversations`
- `GET/PATCH/DELETE /api/v1/conversations/{id}`
- `GET /api/v1/conversations/{id}/messages`
- `POST /api/v1/conversations/{id}/messages/stream`
- `GET /api/v1/agent-runs`
- `GET /api/v1/agent-runs/{run_id}`
- `POST /query_stream`（兼容）
- `GET /healthz`
- `GET /readyz`

运行详情只保存排障所需的脱敏结构化元数据。Prompt 记录文件与 hash，工具记录
输入输出指纹，模型记录耗时和 token；不保存密钥、Authorization、Cookie 或模型
隐式思维链。

## 验证

```powershell
go test ./...
```

上线切换与回滚步骤见
[`docs/operations/agent-runtime-rollout.md`](../docs/operations/agent-runtime-rollout.md)。
