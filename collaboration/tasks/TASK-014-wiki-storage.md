---
id: TASK-014
title: 建立个人空间与结构化上下文存储基础
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-009
source_todos:
  - "docs/product/recruiting-mvp.md#7.2：我的空间"
  - "docs/product/recruiting-mvp.md#8：最小数据范围"
  - "docs/decisions/ADR-014：递归个人空间"
  - "docs/architecture/unified-agent-skill-architecture.md#11：产品数据"
risk: high
review_gate: required
codex_e2e: not_applicable
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/documents/**
  - go-backend/internal/platform/postgres/wiki_*.go
  - go-backend/internal/platform/postgres/document_*.go
  - go-backend/internal/platform/postgres/*wiki*_test.go
  - go-backend/internal/platform/postgres/*document*_test.go
  - go-backend/internal/platform/postgres/migrations/*_personal_space_foundation.sql
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

# TASK-014：个人空间与结构化上下文存储

## 目标

在 Go 产品控制面建立递归 `SpaceFolder`、`MarkdownDocument`、Document Revision 以及
Wiki Item/Revision/Source 的统一存储基础。文档是用户可见内容，Wiki Item 是经确认后
供 ContextPackage 使用的结构化索引；两者可关联但不能互相冒充。

## 最小模型

`SpaceFolder` 至少包含：

- stable ID、user ID、parent folder ID；
- name、规范化 sibling key；
- created/updated/last_opened 时间；
- 并发版本。

`MarkdownDocument` / Revision 至少包含：

- stable ID、user ID、parent folder ID、name/title；
- Markdown 正文或受控存储引用；
- source、原始安全相对路径、content hash、size、media type；
- current revision、created/updated/last_opened 时间；
- extraction 状态与并发版本。

Wiki Item 至少包含：

- stable ID、user ID；
- type：`confirmed_fact/current_state/personal_rule/ai_analysis`；
- domain、当前 revision；
- status：`candidate/confirmed/rejected/outdated/forgotten`；
- confirmation、created/updated/effective 时间；
- 可选 Document/DocumentRevision 来源关联。

Revision/Source 必须记录原始来源、版本、创建者、时间和替代/冲突关系，不复制不必要
的敏感 Runtime 数据。

## 树与路径不变量

- 所有 Folder、Document、Wiki 查询强制 user ID；
- 根目录是用户逻辑边界，不接受跨用户 parent；Document 必须归属一个 Folder；
- 禁止目录环、自己作为祖先、绝对路径、`..` 逃逸和不受控路径拼接；
- 同一父目录下 Folder/Document 的规范化名称冲突有确定结果，不静默覆盖；
- 当前路径由稳定 ID 和父子关系推导，本地绝对路径不是产品身份；
- 深度、单段名称、总路径、文档大小和用户对象数量必须可配置且有上限；
- 移动/重命名使用事务和乐观锁，失败不产生孤儿或半棵树；
- 第一版只允许删除空文件夹；永久删除文档必须二次确认且不静默删除由其产生但已独立
  确认的 Wiki Item。

## Wiki 数据不变量

- Runtime Checkpoint 不是长期记忆；
- AI 分析不能静默变成 confirmed fact；
- 更新当前状态保留历史 Revision；
- `forgotten` 保留内容和历史，但退出默认列表、搜索、ContextPackage 和派生索引；
- 永久删除 Wiki Item 清除正文、Revision/Source 正文和派生索引，只保留无内容、摘要
  或可逆 Hash 的最小 tombstone；
- 暂时遗忘、恢复和永久删除只能由用户操作，Agent 与 Proposal 接受流程不能调用；
- 删除 Wiki Item 不静默级联删除独立 Conversation、Run、Decision 或 Document。

## 非目标

- 不实现 HTTP API 或页面；
- 不实现导入编排、AI 提取、Proposal 或 Context Package；
- 不实现向量检索；
- 不向 Agent 开放 Document CRUD；
- Python 不直接访问这些表。

## 验收标准

- [ ] Migration 可前滚，覆盖干净库和已有库，不改写历史 Migration；
- [ ] Folder/Document/Wiki Store 强制 user ID；
- [ ] 任意深度父子关系、路径推导、名称冲突和目录环有测试；
- [ ] 移动、重命名、文档 Revision 和并发冲突事务一致；
- [ ] 删除空文件夹、非空拒绝和文档删除范围有测试；
- [ ] Wiki 类型、状态机、Revision、Source、遗忘/恢复/永久删除不变量保持；
- [ ] 文档与结构化事实互相可追溯但生命周期独立；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
```

需要真实 PostgreSQL 的测试结果单独列出。Task 进入 `ready` 时按当时 Migration 目录
分配下一个序号，并把通配文件名收窄为唯一 Migration；禁止改写已有 Migration。

## Codex验收与E2E

本 Task 没有用户入口，`codex_e2e: not_applicable`。Codex 独立审查 Schema、树不变量、
数据所有权、并发、删除与用户隔离；页面 E2E 在 TASK-015/017。

## Handoff

写入 `collaboration/handoffs/TASK-014-round-1.md` 后停止。
