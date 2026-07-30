---
id: TASK-014
title: 建立 Wiki Item Revision Source 产品存储
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-009
source_todos:
  - "docs/product/recruiting-mvp.md#8：最小数据范围"
  - "docs/architecture/unified-agent-skill-architecture.md#11：产品数据"
  - "docs/architecture/unified-agent-skill-architecture.md#12：状态所有权"
risk: high
review_gate: required
codex_e2e: not_applicable
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/platform/postgres/wiki_*.go
  - go-backend/internal/platform/postgres/migrations/*_wiki_foundation.sql
  - go-backend/internal/platform/postgres/*wiki*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - collaboration/handoffs/TASK-014-*.md
forbidden_paths:
  - frontend/**
  - backend/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-014：Wiki 产品存储

## 目标

在 Go 产品控制面建立最小 Wiki Item、Revision 和 Source 模型，形成用户长期信息的
唯一事实源和可追溯历史。

## 最小模型

Wiki Item 至少包含：

- stable ID、user ID；
- type：`confirmed_fact/current_state/personal_rule/ai_analysis`；
- domain；
- 当前内容或当前 revision；
- status：`candidate/confirmed/rejected/outdated/forgotten`；
- confirmation 状态；
- created/updated/effective 时间。

Revision/Source 至少记录：

- 原始来源类型和稳定引用；
- 内容版本；
- 创建者：user/system/agent；
- 发生时间；
- 替代或冲突关系；
- 不复制不必要的敏感运行数据。

## 数据不变量

- 所有查询强制用户隔离；
- Runtime Checkpoint 不是长期记忆；
- AI 分析不能静默变成 confirmed fact；
- 更新当前状态保留历史 Revision；
- `forgotten` 表示用户主动暂时遗忘：保留内容和 Revision，默认列表、搜索、
  ContextPackage 和派生索引全部排除，并允许用户恢复到遗忘前状态；
- 永久删除不是可恢复状态：删除 Wiki Item、Revision、Source 中的正文及派生索引，
  只允许保留不含内容、摘要或可逆 Hash 的最小 tombstone；
- 暂时遗忘、恢复和永久删除只能由用户操作；Python Agent 和 Proposal 接受流程均
  不能调用这些操作；
- 永久删除只作用于用户明确选择的产品对象，不静默级联删除独立的 Conversation、
  Run、Decision 或原始 Document；页面必须准确说明删除范围；
- Migration 可向前执行，不破坏现有 app_core 数据。

## 非目标

- 不实现 HTTP API 或页面；
- 不实现向量检索；
- 不实现 Markdown；
- 不实现 Proposal；
- Python 不直接访问这些表。

## 用户操作语义

```text
暂时遗忘
→ 可恢复
→ 不进入未来回答和默认页面
→ 保留原内容与历史

恢复
→ 回到遗忘前状态
→ 重新进入符合条件的默认查询和 Context

永久删除
→ 二次确认
→ 删除本 Wiki 对象的正文、历史正文、来源正文和派生索引
→ 不可恢复
```

最小 tombstone 仅用于删除幂等和安全审计，最多保留对象 ID、用户 ID、删除时间和执行
用户，不得保留原文、摘要、Embedding 或可还原内容。

## 验收标准

- [ ] Migration 和回滚/前滚说明完整；
- [ ] Store/Service 强制 user ID；
- [ ] 类型和状态机强校验；
- [ ] Revision 与 Source 可追溯；
- [ ] 暂时遗忘后默认查询和 Context 均不可见，恢复后回到原状态；
- [ ] 永久删除清除正文与派生索引且不可恢复，只留下无内容 tombstone；
- [ ] Agent 身份不能调用遗忘、恢复或永久删除；
- [ ] 冲突、过期、遗忘、恢复和删除行为有测试；
- [ ] 并发更新有明确乐观锁或事务策略；
- [ ] Migration 测试覆盖干净库和已有库；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
```

需要真实 PostgreSQL 的测试结果单独列出。

Task 进入 `ready` 时按当时 Migration 目录分配下一个序号，并把
`*_wiki_foundation.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

本Task没有用户入口，`codex_e2e: not_applicable`。Codex 独立审查 Schema、状态机、
数据所有权、并发和用户隔离；API/UI E2E 在 TASK-015。

## Handoff

写入 `collaboration/handoffs/TASK-014-round-1.md` 后停止。
