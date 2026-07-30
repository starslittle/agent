# TASK-003 Review Round 2

## 结论

`accepted`

Round-1 的交叉幂等身份 P1 已关闭。结合累计代码审查、真实 PostgreSQL integration、
本地 Create API E2E 和旧聊天页面回归，TASK-003 的全部验收标准已满足。

## Review 输入

- Task base：`ce31efb363c81643e6ec495b2095a6dbf1f2d383`；
- 授权提交：`30d5c4a`；
- 主实现：`d4bcdafea3917941d3d3527550ee5f3508c61ce9`；
- Round-1 Review：`94bab3d`；
- Round-2 fix：`d80c34c44552954a8b276b3a354ee5de22e5207f`；
- Round-2 Handoff：`f1bac6f`；
- 分支：`codex/TASK-003-run-create-supervisor`；
- 工作树：Review 开始时干净。

用户明确要求由 Codex 连续实现并审查至 accepted，因此本 Task 没有 Grok/Codex
人员级隔离；Review 仍按独立提交范围、真实 diff、自动门禁和产品 E2E 分阶段执行，
并在 Round-1 输出实际 `changes_requested` 后通过独立 fix/Handoff gate 关闭。

## Findings

无阻断问题。

## Round-1 Finding 关闭证据

- replay 返回前同时验证已有 user message 的 `client_message_id`、Run 的
  `idempotency_key`、content 和显式 agent；
- PostgreSQL integration 构造同一会话的两条 Run，并把第一条 client ID 与第二条
  idempotency key 交叉组合；
- 交叉组合返回 `ErrIdempotencyConflict`，没有复用任何 Run 或新增消息。

## 验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| Create API 在启动流之前返回稳定 Run 身份 | 通过 | API 返回 queued + run/execution/message IDs；Runtime 后台启动 |
| 创建消息和 Run 事务一致 | 通过 | 单 PostgreSQL transaction；integration 验证 1 Run + 2 messages |
| Supervisor 独立于 HTTP 连接运行 | 通过 | Supervisor 使用 server lifecycle context；Create request cancel 后仍 completed |
| 重复创建不产生重复消息或 Run | 通过 | 相同身份 replay 返回同一组 IDs；交叉身份冲突 |
| Go 重启扫描并恢复/对账到明确终态 | 通过 | running Resume 测试、EOF Snapshot reconciliation 测试 |
| 重启恢复和重复 claim 有自动测试 | 通过 | restart、snapshot、two-supervisor claim 和 PostgreSQL takeover |
| 旧入口继续兼容 | 通过 | 既有 stream tests、detached disconnect test、真实聊天 UI |
| 跨用户和 CSRF 权限正确 | 通过 | Create API integration 覆盖 404/403 |
| 不修改禁止范围 | 通过 | 未修改 frontend、Python Runtime/Workflow、Migration 或 Compose |

## 架构与数据边界复核

- Go 继续拥有 Product Run、message 和终态事实；
- Python 只通过既有 V1 Client 执行模型/工具/LangGraph；
- Supervisor 没有执行任何 Workflow 节点；
- PostgreSQL `FOR UPDATE SKIP LOCKED` + owner/lease epoch 是唯一 owner 来源；
- 所有 Supervisor 写入受 owner/epoch fencing，进程内状态不决定分布式所有权；
- answer checkpoint 与非持久 event cursor 保持恢复一致；
- terminal Runtime Event 不提前把 Product Run 标成终态，Run/message 由同一 Finish
  transaction 一起收敛；
- unmanaged 兼容入口不被 Supervisor 抢占；重启时失败关闭，managed Run 进入恢复；
- 没有新增第二套 Root Graph、模型 Gateway、数据库表或 Migration。

## 自动验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd go-backend && go vet ./...` | 通过 |
| 临时独立 PostgreSQL 数据库中 `go test -p 1 -count=1 ./...` | 通过，integration 实际运行 |
| `git diff --check ce31efb..f1bac6f` | 通过 |
| `go test -race -count=1 ./internal/runs` | 环境不适用：Windows Go 为 `CGO_ENABLED=0` |

临时 PostgreSQL 数据库均在每次验证后删除，没有触碰开发库业务数据。

## Codex 产品级 E2E

环境：

- `C:\Users\10245\Desktop\qidianAgent`；
- 本地开发 Compose；
- gateway 已重启并确认健康；
- `AGENT_PROTOCOL_MODE=v1`；
- 未修改生产配置。

结果：

1. 使用真实 Session/CSRF 创建 conversation；
2. Create Run 首次返回 `queued`、协议版本 1 和稳定身份；
3. 相同请求立即重试，Run、execution、user/assistant message IDs 均未改变；
4. Create HTTP 请求生命周期结束后继续轮询，Run 最终为 `completed`；
5. assistant message 最终为 `completed`，持久正文为
   `TASK003后台执行通过`；
6. 浏览器旧聊天入口随后完成 `TASK003旧入口通过`，证明 Supervisor 没有抢占兼容
   stream 路径；
7. E2E 临时账号和其级联测试数据已按精确邮箱清理，残留计数为 0。

TASK-003 不实现浏览器 Attach，故页面不能直接展示新 Create Run 的实时事件；该项是
TASK-004/TASK-005 的冻结范围，不构成本 Task 缺口。

## 风险与后续门禁

- JSONB lease 在当前 Schema 内满足正确性；未来若需要大规模 expiry 索引，必须取得
  Migration 授权后另行实施。
- TASK-004 仍为 `draft`，未启动。TASK-003 accepted 不构成自动授权。
- ROUND-01 尚未完成，不执行本轮完整 E2E、回滚演练或生产切换。
- 当前分支未推送。
