---
id: ROUND-03
title: 个人 Wiki、Markdown 与确认写入
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds:
  - ROUND-02
tasks:
  - TASK-014
  - TASK-015
  - TASK-016
  - TASK-017
  - TASK-018
  - TASK-019
  - TASK-020
codex_round_e2e: required
user_gate: required
---

# ROUND-03：个人 Wiki、Markdown 与确认写入

## 业务结果

用户可以维护自己的长期信息、导入一篇 Markdown，并决定 AI 提取的候选信息是否
进入 Wiki。Agent 只使用符合状态和授权的最小个人上下文，历史 Run 冻结实际使用的
Revision。

## 主验收旅程

1. 新增、编辑、搜索、查看历史、标记过期、暂时遗忘、恢复和永久删除 Wiki Item；
2. 导入一篇 Markdown，刷新后文档和来源仍存在；
3. Agent 从文档提取候选信息，但不直接写 confirmed Wiki；
4. 分别执行接受、修改后接受、暂缓和拒绝；
5. 重复提交、并发冲突和网络失败不会产生半写入；
6. 发起对话并查看实际使用的 Context Item/Revision；
7. outdated、rejected、forgotten 和未确认内容默认不进入 Context；
8. 修改当前 Wiki 后，历史 Run 仍引用当时 Revision；
9. 验证跨用户 Wiki、Document、Proposal 和 Context 访问被拒绝。
10. 验证暂时遗忘可恢复，永久删除不可恢复，且两种操作都不能由 Agent 触发。

## 必须回归

- ROUND-02 Direct/Research/Fortune 和 Agent Runs；
- Wiki 不存在或 Context 为空时安全退化；
- 关闭 Context 注入后普通 Agent 仍能回答；
- Fortune narrative 不会自动写成 confirmed fact。

## 能力控制与回滚

逻辑控制：

- `personal_wiki_enabled`；
- `wiki_context_injection_enabled`；
- `wiki_proposal_write_enabled`。

发生模型上下文质量问题时优先只关闭 Context 注入，保留 Wiki 管理。发生 Proposal
写入问题时停止接受新 Proposal，保留只读列表和已经确认的 Revision。只有 Wiki
整体入口有严重问题时才关闭 `personal_wiki_enabled`。

回滚不删除 Wiki、Revision、Source、Document、Proposal 或 ContextUsage 数据，不
执行破坏性 Schema 降级。上一轮统一 Agent 必须在新 Schema 保留时继续工作。

## 完成标准

- 所有 Task `accepted`；
- 主验收旅程通过；
- ROUND-02 核心回归通过；
- Context 注入与 Proposal 写入可以分别关闭；
- 关闭后用户数据和审计历史保持完整；
- 形成“了解用户的 Agent”稳定基线；
- 停止并等待用户是否进入 ROUND-04。
