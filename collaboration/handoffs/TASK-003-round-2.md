# TASK-003 Round-2 Handoff

## 状态

`ready_for_review`

- Review input：`94bab3d`
- Fix commit：`d80c34c44552954a8b276b3a354ee5de22e5207f`
- Branch：`codex/TASK-003-run-create-supervisor`

## 修复

关闭 Round-1 唯一 P1：

- replay 查询现在同时读取已存在 user message 的 `client_message_id`；
- 只有 `client_message_id`、`idempotency_key`、content 和显式 agent 全部绑定到同一
  Run 时才返回 replay；
- 任一身份错配返回 `ErrIdempotencyConflict`；
- PostgreSQL integration 新增同一会话两条 Run 后，把第一条
  `client_message_id` 与第二条 `idempotency_key` 交叉组合的场景，确认不会错误复用
  第二条 Run。

没有修改 API、Supervisor、lease、状态机、Migration、Python、前端或生产配置。

## 验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd go-backend && go vet ./...` | 通过 |
| 临时独立 PostgreSQL 数据库中 `go test -p 1 -count=1 ./...` | 通过 |
| `git diff --check` | 通过 |

TASK-004 仍为 `draft`，未启动。
