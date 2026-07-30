---
id: ROUND-05
title: Review 复盘闭环
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds:
  - ROUND-04
tasks:
  - TASK-025
  - TASK-026
codex_round_e2e: required
user_gate: required
---

# ROUND-05：Review 复盘闭环

## 业务结果

用户可以为历史 Decision 录入实际行动和结果，Agent 对照当时依据进行复盘，并把新的
认识作为 Proposal 交给用户确认。历史 Decision 不被重写。

本轮属于 P1，不阻塞秋招最小 MVP。

## 主验收旅程

1. 打开一个已保存的历史 Decision；
2. 录入实际行动、结果和发生时间；
3. 启动 Review Run；
4. 查看 expected/actual、假设验证、新证据和 Lessons；
5. 检查 Review 使用的是当时 Context 与当前事实的明确分层；
6. 接受或拒绝 Wiki/Rule Proposal；
7. 刷新后 Review Record、Run 和 Proposal 仍可追溯；
8. 确认原 Decision、当时 Context 和用户选择没有被改写；
9. 验证重复触发、失败、取消和跨用户拒绝。

## 必须回归

- ROUND-04 完整 Decision 保存和历史展示；
- Proposal 仍只能由用户确认；
- Review 失败不影响 Decision 和 Wiki；
- 不根据单次结果自动生成永久人格标签或修改 Skill。

## 能力控制与回滚

逻辑控制：

- `review_skill_enabled`。

关闭后停止创建新 Review Run 和 Review Record，历史 Review 可以按隐私策略只读；
Decision、Wiki、统一 Agent 和 Runtime 均继续工作。

回滚不删除 Review Record、结果、Proposal、历史 Decision 或 Wiki Revision。

## 完成标准

- TASK-025、TASK-026 均为 `accepted`；
- 主验收旅程和 ROUND-04 核心回归通过；
- Review 能力关闭/重新启用演练通过；
- 形成“能持续复盘的 Agent”稳定基线；
- 停止，后续新业务重新形成 Round。
