---
id: ROUND-02
title: 统一 Agent、Skill 与观测
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds:
  - ROUND-01
tasks:
  - TASK-001
  - TASK-008
  - TASK-009
  - TASK-010
  - TASK-011
  - TASK-012
  - TASK-013
  - TASK-028
codex_round_e2e: required
user_gate: required
---

# ROUND-02：统一 Agent、Skill 与观测

## 业务结果

用户只面对一个启点助手，不再选择永久的普通/深度 Agent 模式。助手可以 Direct
Answer，也可以自动或显式使用 Research/Fortune；用户能查看自己的 Run，内部人员
可以通过同一脱敏投影进行只读诊断。

## 进入门禁与实施顺序

- ROUND-01 必须先完成全部 Task、唯一一次 Round 产品 E2E、回滚演练并达到
  `accepted`；
- 用户必须单独授权 ROUND-02；
- 不在 ROUND-01 夹带奇点 AI → 启点的品牌与页面外壳迁移；
- 先完成 Skill 契约、Model Catalog、Skill Run 协议、Root Resolver 和现有 Skill
  接入；
- TASK-012 在真实协议稳定后，一次完成启点品牌/页面外壳和统一 Skill 交互；
- TASK-012 的未登录首页只复用工作区外壳做静态预览并提供登录入口；现有未登录
  对话概念稿保留给未来落地页设计，本轮不实现游客输入或登录后续接；
- TASK-013、TASK-028 随后完成用户 Agent Runs 和内部观测；
- Wiki、Context、Proposal 和 Decision 继续等待各自业务 Round，不在前端伪造。

详细决策见
[`ADR-013`](../../docs/decisions/ADR-013-qidian-frontend-migration-sequence.md)。

## 主验收旅程

1. 未登录访问显示工作区静态预览和右上角登录入口，不读取私有数据、不允许游客
   发送问题；登录成功后进入真实工作区；
2. 普通问题进入 Direct Answer，默认不联网、不调用工具；
3. 显式选择 Research，展示 Skill Chip、结构化 Activity 和 Citation；
4. 通过自然语言自动选择 Research，并展示选择来源；
5. 显式选择 Fortune；自动识别 Fortune 时先确认；
6. 移除 Skill Chip 后恢复自动路由；
7. 未知 Skill、路由模型失败和低置信度安全回退；
8. 刷新、取消和失败继续遵守 ROUND-01 Run 语义；
9. 普通用户在 Agent Runs 中只能查看自己的历史；
10. `observability_admin` 可以筛选脱敏 Run，普通用户访问内部 API 被拒绝；
11. 页面和事件不展示隐藏思维链、完整 Prompt 或敏感载荷；
12. 登录、应用外壳和对话页统一使用启点品牌，不再出现奇点 AI、轨道图形或 Lovable
    遗留 metadata；
13. 页面不出现尚不可用的 Wiki、Proposal 或 Decision 入口，移动端和深浅色可用。

## 必须回归

- ROUND-01 完成、刷新、断线、取消、失败和 Citation；
- 旧 `agent_name` 在兼容窗口内仍能通过 Adapter 读取/请求；
- Research/Fortune Workflow 本身没有被重写；
- 用户 Run 所有权和管理员只读边界。
- ROUND-01 对话、Activity、Citation、取消和恢复在启点外壳中保持原语义。

## 发布控制与兼容

2026-08-01 产品决定：本轮暂不实现 `unified_agent_enabled` 和
`agent_observability_enabled`。统一助手是唯一用户入口，不通过恢复旧 Agent 选择或
静默切换处理路径增加用户心智；内部观测以服务端 `observability_admin` 角色作为
访问边界，普通用户没有入口且内部 API 必须返回拒绝。

本轮验收不要求两个能力开关的关闭/重新启用演练，改为验证：

1. Root Skill 路由、显式 Skill 和安全回退在统一入口内行为稳定；
2. 普通用户与内部观测的前后端权限边界不可绕过；
3. 历史新旧 Run 均可按兼容策略读取；
4. 新 Run 的 requested/resolved Skill 和 provenance 正确。

生产级灰度、紧急停止或版本回退机制在发布准备阶段单独设计；不得为了回退而在本轮
重新向用户暴露旧 Agent 选择器。Migration 继续遵守 Expand–Migrate–Contract，任何
发布回退都不得删除 Skill Manifest、Run Snapshot、新协议字段或历史数据。

## 完成标准

- 所有 Task `accepted`；
- 主验收旅程通过；
- ROUND-01 完整核心回归通过；
- 统一入口、兼容读取和管理员权限边界通过验收；
- 形成“通用 Agent”稳定基线；
- 停止并等待用户是否进入 ROUND-03。
