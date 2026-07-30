# TASK-003 Review Round 1

## 结论

`changes_requested`

主体实现满足 Create/事务/Supervisor/lease/restart/权限和旧入口兼容要求，自动门禁与
本地 E2E 均已通过。但幂等查找在 `client_message_id` 和 `idempotency_key` 分别命中
不同 Run 时可能错误复用其中一条，需先关闭这一数据完整性边缘条件。

## Review 输入

- Task base：`ce31efb363c81643e6ec495b2095a6dbf1f2d383`；
- 授权提交：`30d5c4a`；
- 实现提交：`d4bcdafea3917941d3d3527550ee5f3508c61ce9`；
- Handoff 提交：`844dee6`；
- 分支：`codex/TASK-003-run-create-supervisor`；
- TASK-004 仍为 `draft`，未启动。

## 已通过项

- Create API 在事务提交后立即返回稳定 Run/execution/message 身份；
- user message、assistant message 和 Product Run 事务一致；
- HTTP 请求结束不取消 Supervisor；
- PostgreSQL claim/lease/epoch 和旧 owner fencing；
- Go 启动扫描、Resume 和 Runtime Snapshot 对账；
- 重复 Supervisor claim 只启动一次；
- CSRF、跨用户和单活动 Run 约束；
- 旧 `/messages/stream` 保持兼容；
- 未修改 Migration、Python、前端、Compose 或生产配置。

## Finding

### P1：交叉幂等身份可能错误复用 Run

`loadIdempotentGeneration` 使用
`client_message_id = $2 OR idempotency_key = $3` 查找，并优先返回
`idempotency_key` 命中的记录，但没有确认返回记录的 client message ID 同时等于
本次请求值。

若请求把 Run A 的 `client_message_id` 与 Run B 的 `idempotency_key` 交叉组合，
并让内容匹配 Run B，查询会返回 Run B，而不是报告幂等冲突。这样会破坏
`client_message_id/idempotency_key` 对同一创建身份的绑定。

## 必须修改

1. 幂等 replay 必须确认 `client_message_id`、`idempotency_key`、内容和显式 agent
   全部对应同一 Run；任一身份错配返回 `ErrIdempotencyConflict`。
2. 增加或扩展真实 PostgreSQL integration，覆盖身份 key 改变或交叉组合时不会复用
   原 Run。
3. 复跑 Go 单元、vet、真实 PostgreSQL integration 和 `git diff --check`。
4. 写入 `collaboration/handoffs/TASK-003-round-2.md` 后进入下一次 Review。
