# TASK-003 Round-1 Handoff

**Status**: ready_for_review
**Executor**: Codex（用户明确要求不再由 Grok 接管，并连续执行至 accepted）
**Business round**: ROUND-01
**Task base**: `ce31efb363c81643e6ec495b2095a6dbf1f2d383`
**Authorization commit**: `30d5c4a`
**Implementation commit**: `d4bcdafea3917941d3d3527550ee5f3508c61ce9`
**Branch**: `codex/TASK-003-run-create-supervisor`
**Date**: 2026-07-31

## 交付行为

- 新增 `POST /api/v1/conversations/{conversation_id}/runs`：
  - 在同一个 PostgreSQL 事务中创建 user message、streaming assistant message 和
    Product Run；
  - 首次返回 `run_id`、`execution_id`、两条 message ID、初始状态和协议版本；
  - 只在 `AGENT_PROTOCOL_MODE=v1` 下开放，不改变生产默认协议模式；
  - 保持 Session、CSRF 和 conversation user ownership 边界。
- Create Run 按 `client_message_id + idempotency_key` 幂等：
  - 相同请求返回原有稳定身份，不重复创建消息或 Run；
  - 相同 key 但内容或显式 agent 不同返回 `idempotency_conflict`。
- 新增 Go Run Supervisor：
  - HTTP Handler 只负责事务创建和异步提交，不持有 Python execution 生命周期；
  - Supervisor 使用自身服务生命周期 context 启动/恢复 Runtime；
  - 浏览器/Create HTTP 请求结束不会取消后台 Run；
  - Go 启动后扫描 Supervisor-managed 的 queued/running/cancel_requested Run；
  - queued 使用 Start，已有活动 Run 使用 `starting_after=last_sequence` Resume；
  - replay 结束或打开失败时通过 Runtime Snapshot 对账明确终态；
  - answer checkpoint 与 `last_sequence` 原子推进。
- 多 Gateway 所有权使用 PostgreSQL 原子 claim/lease：
  - owner ID、lease epoch 和 expiry 保存于现有 `agent_runs.metadata`；
  - `FOR UPDATE SKIP LOCKED` 保证唯一 claim；
  - lease epoch 单调递增；
  - checkpoint、cursor、event 和 terminal write 校验 owner/epoch，旧 owner 被 fencing；
  - 没有使用进程内 map 作为分布式所有权来源。
- 旧 `/messages/stream` 保持兼容：
  - 新建记录明确标记是否由 Supervisor 管理；
  - Supervisor 不 claim 旧 Handler 正在拥有的 Run；
  - Go 重启时，无法恢复的旧 unmanaged Run 失败关闭，managed Run 交给 Supervisor
    恢复；
  - 既有断线后 detached resume 测试继续通过。
- 未新增或修改数据库 Migration；现有 `metadata`、`execution_id`、
  `idempotency_key`、`last_sequence` 和 active-run unique index 足以实现本 Task
  不变量。

## 修改文件

- `go-backend/cmd/server/main.go`
- `go-backend/internal/conversation/service.go`
- `go-backend/internal/conversation/store.go`
- `go-backend/internal/conversation/types.go`
- `go-backend/internal/httpapi/conversations.go`
- `go-backend/internal/httpapi/server.go`
- `go-backend/internal/httpapi/conversation_integration_test.go`
- `go-backend/internal/platform/postgres/conversation_store.go`
- `go-backend/internal/platform/postgres/run_supervisor_store.go`
- `go-backend/internal/platform/postgres/run_supervisor_store_integration_test.go`
- `go-backend/internal/runs/supervisor.go`
- `go-backend/internal/runs/supervisor_test.go`

## 自动验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd go-backend && go vet ./...` | 通过 |
| 临时独立 PostgreSQL 数据库中 `go test -p 1 -count=1 ./...` | 通过，真实 PostgreSQL integration 已运行 |
| `git diff --check` | 通过 |
| `go test -race -count=1 ./internal/runs` | 未运行：当前 Windows Go 环境 `CGO_ENABLED=0`，race detector 不可用 |

新增自动化覆盖：

- Go 重启后扫描 running Run 并从持久 sequence 恢复；
- replay 已结束时通过 Runtime Snapshot 对账终态；
- 两个 Supervisor 竞争时只启动一次 Runtime；
- PostgreSQL owner takeover 后旧 epoch 无法继续写；
- Create 重试返回同一 Run/execution/message 身份且只创建 1 Run + 2 messages；
- 请求 context 结束后后台 Run 继续完成；
- Create API 的 CSRF 和跨用户访问拒绝；
- Supervisor 与旧 `/messages/stream` 兼容；
- unmanaged 旧 Run 不被 Supervisor claim，重启时明确失败关闭。

## 本地验收证据

在正确挂载 `C:\Users\10245\Desktop\qidianAgent` 的本地 V1 Compose 环境：

1. 真实 Create API 首次返回 `queued` 和协议版本 1；
2. 相同请求立即重试，Run、execution 和 message 身份保持一致；
3. Create HTTP 请求结束后，后台 Run 和 assistant message 最终均为 `completed`；
4. 持久正文精确为 `TASK003后台执行通过`；
5. 旧聊天 UI 随后通过 `/messages/stream` 正常完成
   `TASK003旧入口通过`；
6. E2E 临时账号及其级联 conversation/message/run 数据已按精确邮箱删除。

## 偏差、风险与后续

- TASK-004 才负责浏览器 Attach/Re-attach；TASK-003 没有新增 events GET API。
- TASK-005 才负责把前端切换到 Create + Attach；当前页面继续使用旧 stream 入口。
- lease 字段保存在现有 JSONB metadata，因此无需 Migration；大规模 Run 数量下若需要
  针对 lease expiry 建专用索引，必须在未来获得 Migration 授权后另行冻结。
- 本 Task 没有修改 Python Workflow、Runtime、前端、Compose、生产配置或协议默认值。
- TASK-004 仍为 `draft`，未启动。

**Round-1 实现已停止，等待 Review gate。**
