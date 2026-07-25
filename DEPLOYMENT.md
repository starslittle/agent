# 部署指南

## 当前部署架构

迁移第一阶段采用双服务、单入口：

```text
Internet
   |
   v
Go Gateway :8000
   |
   v
Python Legacy API :8000（仅容器内部）
   |              \
PostgreSQL       Redis（仅容器内部）
```

Go 负责公网 API、SSE 透传、静态前端、请求 ID、日志和健康检查。Agent、
LLM、RAG 及现有工具仍由 Python 完整执行。

生产环境只发布 Go 的端口。不要单独发布 Python、PostgreSQL 或 Redis。

## 环境变量

复制示例文件：

```powershell
Copy-Item .env.example .env
```

至少填写：

- `DASHSCOPE_API_KEY`
- `POSTGRES_PASSWORD`
- 使用研究、天气能力时填写 `TAVILY_API_KEY`、`SENIVERSE_API_KEY`

`.env` 已被 Git 忽略，只作为本机或 Compose 的单一配置源。生产平台应通过
Secret 管理功能注入真实值，不要把真实值写入镜像、Compose 或仓库。

已经进入过 Git 历史的凭据仍需在外部平台撤销并轮换；更换本地文件并不能
让旧凭据失效。

## 开发环境

```powershell
docker compose -f docker-compose.dev.yml up --build
```

服务地址：

- 前端（Vite 热更新）：`http://localhost:5173`
- Go API：`http://localhost:8000`
- PostgreSQL：`localhost:5432`（仅开发环境发布）
- Redis：`localhost:6379`（仅开发环境发布）

前端源码改动会自动热更新，不需要重新构建。Python 通过 Uvicorn reload
自动重载。Go 源码修改后当前容器需要重启：

```powershell
docker compose -f docker-compose.dev.yml restart gateway
```

## 生产环境

先校验最终配置：

```powershell
docker compose config
```

再构建并启动：

```powershell
docker compose up --build -d
```

验证：

```powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
```

- `/healthz` 只表示 Go 进程存活；
- `/readyz` 还会验证 Python Legacy API 可用；
- 部署平台和负载均衡应使用 `/readyz` 判断是否接收流量。

查看状态和日志：

```powershell
docker compose ps
docker compose logs -f gateway python
```

停止服务：

```powershell
docker compose down
```

不要使用 `down -v`，除非明确要删除 PostgreSQL 数据卷。

## 镜像职责

- `go-backend/Dockerfile`：构建 Go 网关和前端，生成公网镜像；
- `backend/Dockerfile`：构建 Python Legacy API，仅供内部服务使用；
- `docker-compose.yml`：生产拓扑；
- `docker-compose.dev.yml`：开发拓扑与前端热更新。

## 回滚

阶段 1 的 Go 网关不写业务数据。发生网关兼容问题时：

1. 保留 PostgreSQL、Redis 和 Python 服务；
2. 临时把入口路由切回 Python `/query_stream`；
3. 修复 Go 后重新执行 SSE 契约和端到端测试；
4. 再把入口切回 Go。

生产回滚前仍需确保 Python 端口只对受控入口开放，不能把数据库或缓存发布
到公网。
