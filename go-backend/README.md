# Go Gateway

这是 Python → Go 渐进迁移的第一阶段入口。当前 Go 负责：

- `POST /query_stream` 请求校验与 Python SSE 字节透传；
- `GET /healthz` 进程存活检查；
- `GET /readyz` Python 上游就绪检查；
- 请求 ID、结构化日志、panic 恢复和优雅退出；
- 客户端断开时取消发往 Python Legacy API 的 HTTP 请求；
- 生产环境静态前端托管。

当前 Go **尚不执行 Agent、LLM 或 Tool**。请求仍由 Python 的
`stream_graph` 完整处理，后续阶段再逐步把默认 Agent、路由和原生工具迁入
Go。

## 本地手动启动

先让 Python 使用内部端口 8001：

```powershell
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

再启动 Go 公网入口：

```powershell
cd go-backend
$env:HTTP_ADDR = ":8000"
$env:PYTHON_BASE_URL = "http://127.0.0.1:8001"
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
