# 迁移 Backlog 全量审查

> 审查日期：2026-07-30
>
> 范围：TASK-001～TASK-028、业务轮次、依赖图及其直接引用的产品/架构契约
>
> 结论：整体拆分合理；已修正文档级冲突，但所有 Task 仍为 `draft`，不构成执行授权

## 1. 总体结论

当前 28 个 Task 已经覆盖：

- 可靠 Product Run 和浏览器事件；
- Model/Skill 契约与统一 Root Assistant；
- 用户 Run 页面和内部只读观测；
- Wiki、Markdown、Context 和 Proposal；
- Decision 秋招 MVP；
- P1 Review；
- 非生产发布准备。

依赖图没有缺失 Task、重复 ID、环或 Round 归属冲突。每个修改前端页面或交互的 Task
都声明了 `frontend-design`、`ui-ux-pro-max`、`web-design-guidelines`。

原规划存在的主要问题不是 Task 数量，而是少数跨 Task 契约没有写透，以及部分
`allowed_paths` 可能被误解为数据库 Migration 授权。本次已经完成能确定的修正。

## 2. 本次已修正的跨 Task 问题

### 2.1 Direct Answer 不需要 Skill

统一规则修正为：

```text
一次 Run 最多选择一个主 Skill
Direct Answer → resolved_skills=[] / primary_skill=null
```

复数 `resolved_skills` 只为兼容和未来演进保留，不表示 MVP 已支持多 Skill。

### 2.2 未决扩展不进入当前 Task

ExecutionPlan、多 Skill、主 Skill 支持能力、通用 Bounded Action Loop、Run 内持久
HITL、高级上下文规划和 Eval 治理已经单独记录在
[`Agent Core 未来扩展候选`](../../docs/architecture/agent-core-future-options.md)。
这些内容不属于当前 28 个 Task。

### 2.3 Run API 命名统一

创建仍使用会话子资源：

```text
POST /api/v1/conversations/{id}/runs
```

事件和取消复用现有 Agent Run 资源：

```text
GET    /api/v1/agent-runs/{run_id}/events
DELETE /api/v1/agent-runs/{run_id}
```

避免同时出现 `/runs/{id}` 和 `/agent-runs/{id}` 两套详情身份。

### 2.4 自动路由与 Context Package 的先后关系

TASK-016 现在明确：

```text
创建同一 Product Run
→ Python Resolver 使用最小 Routing Context
→ Go 按 SkillResolution 组装并冻结 ContextPackage
→ Python 复用冻结 resolution 执行
```

路由和执行必须复用同一个 Resolver，Python 不读取 Wiki 表，重连不重新路由。

### 2.5 Fortune 自动选择的确认语义

当前 MVP 不增加暂停中的 Product Run 状态。`confirmation_required` Run 在未执行
目标 Skill、Capability 或写操作的情况下完成；用户确认形成一个正常后续 Turn，
并显式携带 `requested_skill`。同 Run 持久暂停/恢复保留为未来候选。

### 2.6 Decision 入口不提前出现

TASK-012 的 ROUND-02 页面只展示当时 available 的 Skill。`/decision` 在 TASK-021
真正启用 Decision Manifest 后通过动态菜单出现，不能在尚无 Workflow 时伪造入口。

### 2.7 Review 的实现与产品接入分开

TASK-025 只建立 `available=false` 的内部 Review Workflow，因此
`codex_e2e: not_applicable`。TASK-026 负责 Go 的 Decision/Context 输入、Review
持久化、Python 启用和真实页面 E2E。

### 2.8 Migration 授权收紧

需要新表或字段的 Task 只允许匹配自身用途的新增 Migration 文件，并要求在进入
`ready` 时按实际目录分配下一个序号、冻结唯一文件名。现有 Migration 不得改写。

TASK-028 不再假设固定使用 `006_agent_observability_access.sql`，因为更早执行的
TASK-009 可能先占用下一个序号。

### 2.9 文档 CRUD 与隐藏权限

用户确认 Agent 的目标能力应包含类似 Codex 的文档创建、修改和删除，但隐藏/恢复
只允许用户手动操作。当前结论是：

- Agent 文档 CRUD 通过受控 Capability、Revision 和 Changeset 实现；
- Agent 主动提出的修改先确认；
- 永久删除必须来自用户明确要求并再次确认；
- `document_hide/document_unhide` 不进入 Capability Registry；
- 该方向已经确认，但实现轮次尚未决定，不扩入 TASK-017。

## 3. 逐 Task 审查

| Task | 审查结论 | 本次处理或进入 ready 前重点 |
|---|---|---|
| TASK-001 | 合理，边界清楚 | 补齐 Manifest 的预算/deadline 字段和校验。 |
| TASK-002 | 合理 | 明确不授权 Migration；Schema 不足时退回重规划。 |
| TASK-003 | 原恢复验收过软 | Go 重启扫描、对账/恢复和重复 claim 改为必须测试。 |
| TASK-004 | 合理 | 事件路径统一为 `/api/v1/agent-runs/{id}/events`；禁止 Migration。 |
| TASK-005 | 清楚合理 | 保持只修改前端 Run 生命周期，不混入统一助手 UI。 |
| TASK-006 | 清楚合理 | 验收 Task 不借机修业务；失败必须产生修复 Task。 |
| TASK-007 | 跨三服务风险原标低 | 风险改为 high；无明确授权不新增 Migration。 |
| TASK-008 | 合理 | 移除不必要的产品 API 修改路径，保持纯 Catalog 基础。 |
| TASK-009 | 协议方向正确 | 写清 Direct 空 Skill、resolution 一次写入、幂等冲突和专属 Migration。 |
| TASK-010 | 原“必须一个 Skill”不准确 | 改为最多一个，并冻结 confirmation_required 的 MVP 语义。 |
| TASK-011 | 清楚合理 | 保持适配现有 Research/Fortune，不重写 Workflow。 |
| TASK-012 | 原先提前要求 `/decision` | 改为只展示 available Skill；Decision 由后续动态出现。 |
| TASK-013 | 验收要求聊天跳转但禁止改聊天 | 改为依赖 TASK-012，并允许修改聊天中的 Run 导航。 |
| TASK-014 | 存储模型合理 | 已冻结手动暂时遗忘/恢复、永久删除不可恢复和无内容 tombstone；新增专属 Migration 边界。 |
| TASK-015 | 页面范围合理 | 暂时遗忘与永久删除分开，均由用户手动；页面明确可恢复性和删除范围。 |
| TASK-016 | 原存在路由/上下文循环依赖 | 补齐 Resolve → Context → Execute、重试不漂移和 Direct Context 规则。 |
| TASK-017 | 合理 | 收紧 Document Store/Migration；Agent 文档 CRUD 需要独立后续 Task，不顺手扩入导入功能。 |
| TASK-018 | 合理 | 收紧 Proposal Store/Migration；事务和幂等边界保持。 |
| TASK-019 | 原 Product Run 关联不清 | 增加 `run_purpose`、document/hash/版本关联和提取幂等。 |
| TASK-020 | 清楚合理 | 四种确认操作和失败恢复边界完整。 |
| TASK-021 | 合理 | 明确 MVP 不做 Research/多 Skill；Proposal 复用既有确认通道。 |
| TASK-022 | 原浏览器输入信任边界未写 | Decision 只能从服务端验证的 Skill Result 投影；收紧 Migration。 |
| TASK-023 | 原“Wiki 中查看 Decision”易误解 | 明确 Decision 是独立对象，只在 Wiki 页面提供关联区域。 |
| TASK-024 | 验收范围合理 | 移除修改全部架构/产品文档的宽权限，只允许验收材料和 README。 |
| TASK-025 | 原 Task 无产品输入却要求 E2E | 改成 unavailable 内部 Workflow，E2E 统一后移。 |
| TASK-026 | 原缺少 Go/Python 接入路径 | 补齐 Decision/Context/Runtime 接入、启用门禁和专属 Migration。 |
| TASK-027 | 清楚合理 | 保持非生产 readiness，不授权生产切换。 |
| TASK-028 | 方案合理 | 修复固定 Migration 编号冲突；保持独立只读权限和审计。 |

## 4. 仍需在执行前冻结的事项

Wiki 的暂时遗忘、恢复和永久删除语义已经由用户确认，不再是产品待决项。

### 4.1 TASK-016 内部 Resolve API

两阶段不变量已经确定，但具体内部路径、签名输入、超时、路由失败回退和
SkillResolution Schema 必须在 TASK-016 进入 `ready` 时基于当时 TASK-009/010
实现冻结。

### 4.2 Migration 文件序号

所有使用 `*_skill_run_protocol.sql`、`*_wiki_foundation.sql` 等用途后缀的 Task，
都必须在各自进入 `ready` 时替换成当时唯一的下一个编号。当前 draft 阶段不提前
占号。

### 4.3 未来 Agent Core 扩展

多 Skill、支持能力、通用 ReAct、Run 内持久 HITL 和 Eval 仍为候选；不得用当前
`resolved_skills` 复数字段或 LangGraph 并行能力推断已经获得实现授权。

### 4.4 Agent 文档 CRUD 的实施轮次

Agent 文档创建、修改和删除是已确认目标，但尚未决定进入当前 MVP、P1 还是独立
业务轮次。进入实现前必须新增 Task，并冻结 Document Capability、Changeset、
Revision、删除确认、隐藏隔离、失败恢复和产品 E2E。

## 5. 当前执行门禁

本次审查不把任何 Task 改为 `ready`。开始 TASK-002 前仍需：

- 当前文档形成 Git 基准提交；
- ROUND-01 获得用户明确授权；
- ROUND-01 和 TASK-002 固定完整 `base_commit`；
- 对照当时代码重新确认路径和测试命令；
- 创建对应 Grok 工作区并一次只执行一个 Task。
