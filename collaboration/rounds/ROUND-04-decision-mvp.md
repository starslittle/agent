---
id: ROUND-04
title: Decision 秋招 MVP 闭环
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds:
  - ROUND-03
tasks:
  - TASK-021
  - TASK-022
  - TASK-023
  - TASK-024
codex_round_e2e: required
user_gate: required
---

# ROUND-04：Decision 秋招 MVP 闭环

## 业务结果

Agent 使用用户确认的 Wiki 和 Markdown 信息分析秋招决策，用户保存自己的最终选择，
确认新的 Wiki 建议，并在下一次对话中使用更新后的信息。

本轮通过后，秋招最小 MVP 才成立。

## 主验收旅程

完整执行产品文档的 12 步唯一链路：

1. Wiki 保存“正在准备 Agent 岗位秋招”；
2. 导入一篇面试复盘 Markdown；
3. Agent 提取候选信息，用户确认；
4. 询问“下一轮优先准备系统设计还是算法”；
5. 自动选择 Decision Skill；
6. 页面展示 Skill 和所用个人上下文；
7. Agent 流式返回分析；
8. Agent Run 展示真实执行步骤；
9. Agent 生成“当前薄弱点”更新建议；
10. 用户确认后 Wiki 更新；
11. 用户保存最终选择；
12. 下一次对话使用更新后的信息。

同时验证显式 `/decision`、无 Context 退化、未保存 Draft、刷新、重复保存、冲突、
取消、失败和跨用户拒绝。

## 必须回归

- ROUND-01 Run 可靠性；
- ROUND-02 统一 Agent、Research/Fortune 和观测；
- ROUND-03 Wiki、Markdown、Proposal 和 Context；
- Decision 不替用户自动保存最终选择；
- 修改 Wiki 不改变历史 Decision 的 Context Revision。

## 能力控制与回滚

逻辑控制：

- `decision_skill_enabled`；
- `decision_write_enabled`。

关闭 Decision Skill 后停止新 Decision Run，Direct/Research/Fortune 和 Wiki 保持
可用。关闭 Decision 写入后，历史 Decision 保持只读，新 Draft 或用户选择保存由
服务端明确拒绝。

回滚不删除 Decision Record、用户选择、Context Revision 或关联 Run。若必须关闭
Wiki/Context，则 Decision 也必须同时关闭，不能留下看似可用但缺少强依赖的入口。

## 完成标准

- TASK-021～TASK-024 全部 `accepted`；
- Codex 使用 Browser / Computer Use 逐步证明 12 步链路；
- 自动测试和真实页面观察一致；
- ROUND-01～03 核心回归通过；
- Decision 执行和写入控制分别演练；
- 形成秋招 MVP 稳定基线；
- 停止，由用户决定进入 ROUND-05 或 RELEASE-GATE。
