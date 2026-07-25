# Go Gateway

这是 Python → Go 渐进迁移的第一阶段入口。当前 Go 负责：

- 注册、登录、退出和会话恢复；
- PostgreSQL 用户、身份凭据与服务端 Session；
- HttpOnly Cookie、CSRF 校验、登录限流和登录审计；
- `POST /query_stream` 请求校验与 Python SSE 字节透传；
- `GET /healthz` 进程存活检查；
- `GET /readyz` Python 上游就绪检查；
- 请求 ID、结构化日志、panic 恢复和优雅退出；
- 客户端断开时取消发往 Python Legacy API 的 HTTP 请求；
- 生产环境静态前端托管。

当前 Go **尚不执行 Agent、LLM 或 Tool**。认证通过后，请求仍由 Python 的
`stream_graph` 完整处理，后续阶段再逐步把默认 Agent、路由和原生工具迁入
Go。

## 本地手动启动

先复制根目录 `.env.example` 为 `.env`，填写 PostgreSQL 密码、模型密钥和
至少 32 字符的 `INTERNAL_AGENT_SECRET`。Go 与 Python 必须使用相同的内部
密钥。

先让 PostgreSQL 可用，再让 Python 使用内部端口 8001：

```powershell
$env:INTERNAL_AGENT_SECRET = "<与 Go 相同的内部密钥>"
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

再启动 Go 公网入口：

```powershell
cd go-backend
$env:HTTP_ADDR = ":8000"
$env:PYTHON_BASE_URL = "http://127.0.0.1:8001"
$env:GO_DATABASE_URL = "postgres://qidian_agent:<密码>@127.0.0.1:5432/agent_db"
$env:INTERNAL_AGENT_SECRET = "<与 Python 相同的内部密钥>"
go run ./cmd/server
```

前端继续运行在 5173，Vite 默认把 API 代理到 Go 的 8000 端口。前端代码修改
会热更新，不需要重新构建。

## 使用 Compose

```powershell
docker compose -f docker-compose.dev.yml up --build
```

开发拓扑：

```text
Browser :5173 -> Vite -> Go :8000 -> Python :8000 (Compose 内部)
```

生产使用 `docker compose up --build -d`。生产环境只有 Go 的应用端口暴露到
宿主机，Python、PostgreSQL 和 Redis 只在 Compose 内部网络开放。

## 配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_ENV` | `ENVIRONMENT`，再回退 `development` | Go 运行环境；迁移期兼容 Python 变量名 |
| `HTTP_ADDR` | 由 `PORT` 生成，默认 `:8080` | Go 监听地址 |
| `PYTHON_BASE_URL` | `http://127.0.0.1:8000` | Python Legacy API |
| `GO_DATABASE_URL` | 从 `POSTGRES_*` 生成 | Go 用户与 Session 数据库；优先于 `DATABASE_URL` |
| `PUBLIC_ORIGINS` | 本地 5173 地址 | 允许发起状态变更请求的前端 Origin |
| `COOKIE_SECURE` | 开发 `false` | 生产必须为 `true` |
| `SESSION_TTL` | `168h` | 登录 Session 有效期 |
| `INTERNAL_AGENT_SECRET` | 无 | Go → Python 请求签名密钥，至少 32 字符 |
| `STATIC_DIR` | 空 | 可选前端构建目录 |
| `MAX_REQUEST_BYTES` | `1048576` | 请求体上限 |
| `UPSTREAM_HEADER_TIMEOUT` | `30s` | 等待 Python 响应头的上限 |
| `SHUTDOWN_TIMEOUT` | `10s` | 优雅退出时限 |

## 验证

```powershell
cd go-backend
go test ./...
```

SSE 契约样例位于
`internal/httpapi/testdata/query_stream_contract.json`。测试会验证请求字段、
请求 ID、CRLF、事件名和 JSON 数据均不被网关改写。

## 认证 API

| 方法与路径 | 作用 | 保护 |
|---|---|---|
| `POST /api/v1/auth/register` | 邮箱密码注册并登录 | Origin 校验 |
| `POST /api/v1/auth/login` | 登录 | Origin 校验、账户与 IP 限流 |
| `GET /api/v1/session` | 恢复前端会话与 CSRF Token | HttpOnly Session Cookie |
| `GET /api/v1/me` | 获取当前用户 | Session |
| `POST /api/v1/auth/logout` | 撤销当前 Session | Session、CSRF、Origin |
| `POST /query_stream` | 发起 Agent 流式请求 | Session、CSRF、Origin |

浏览器不保存 Session Token；它只保存由服务端设置的 HttpOnly Cookie。详细
边界和扩展方式见根目录 `AUTHENTICATION.md`。
