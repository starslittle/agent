---
id: ROUND-01
title: 可信 Agent 运行链路
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds: []
tasks:
  - TASK-002
  - TASK-003
  - TASK-004
  - TASK-005
  - TASK-006
  - TASK-007
codex_round_e2e: required
user_gate: required
---

# ROUND-01：可信 Agent 运行链路

## 业务结果

用户可以可信地完成一次普通或 Research 对话：Activity 与回答正文分离，刷新或断线
可以继续观察执行，取消和失败不会产生伪终态，引用能够稳定保存和再次打开。

这是后续 Skill、Wiki 和 Decision 的运行地基，但验收必须落在真实聊天体验上，而不
只是协议或测试通过。

## 主验收旅程

1. 发起普通对话并确认流式正文完整；
2. 发起 Research 对话并确认 Activity、正文和 Citation 分层；
3. 运行中刷新页面并从最后 sequence 重新附着；
4. 模拟订阅断开，确认后台 Run 不被误取消；
5. 正常取消、取消失败重试和取消/完成竞态均显示真实终态；
6. 模拟 Runtime 失败和超时，确认消息、Run 和会话一致且下一条消息可发送；
7. 刷新后重新查看正文和 Citation；
8. 验证跨用户 Run/Event/Message 访问被拒绝。

TASK-006 的自动报告是本轮证据之一，不能替代 Codex 的 Browser / Computer Use
验收。

## 必须回归

- 登录、历史会话和普通聊天；
- Research 现有核心结果；
- Fortune 现有入口不因 Run 协议迁移失效；
- 消息复制内容只包含回答正文；
- 用户隔离和脱敏。

## 能力控制与回滚

优先使用现有 Runtime 协议/部署控制在 `legacy` 与 `v1` 间切换。进入 `ready` 前必须
确认浏览器和 Go/Python 的兼容组合，不能只切后端而留下不可用前端。

回滚演练：

1. 保留新增 Runtime/Product Run Schema；
2. 停止创建新的 v1 Run；
3. 让进行中的 Run 到达明确终态或按计划取消；
4. 切回上一 accepted 的完整应用组合；
5. 验证普通对话、历史消息和用户隔离；
6. 再次启用 v1 并验证新 Run。

不通过 Down Migration 删除 event、checkpoint、trace 或历史 Run。

## 完成标准

- 所有 Task `accepted`；
- 主验收旅程和必须回归项通过；
- 自动 P0 报告没有伪通过；
- 回滚和重新启用演练通过；
- 记录 accepted commit；
- 停止并等待用户是否进入 ROUND-02。
