---
id: TASK-018
title: 建立 Wiki Update Proposal 状态机与事务写入
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-014
source_todos:
  - "docs/product/recruiting-mvp.md#9：Memory Proposal"
  - "docs/architecture/unified-agent-skill-architecture.md#2.5：AI只提出更新建议"
  - "docs/architecture/unified-agent-skill-architecture.md#11：产品数据"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/proposals/**
  - go-backend/internal/httpapi/proposal*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/platform/postgres/proposal_*.go
  - go-backend/internal/platform/postgres/*proposal*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_wiki_proposal.sql
  - collaboration/handoffs/TASK-018-*.md
forbidden_paths:
  - frontend/**
  - backend/**
  - go-backend/internal/conversation/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-018：Wiki Proposal 状态机

## 目标

建立由 Go 拥有的 Wiki Update Proposal、状态机和确认事务，使 Agent 只能提出“我的
空间”背后的长期结构化信息变更，不能直接提交用户事实。Proposal 与来源 Document/
DocumentRevision 可追溯，但不直接修改 Markdown 原文。

## 状态与操作

建议状态：

```text
pending
accepted
rejected
deferred
superseded
```

用户操作：

- 原样接受；
- 修改后接受；
- 暂缓；
- 拒绝。

接受时在同一事务中：

- 校验 Proposal 仍可处理；
- 创建或更新 Wiki Item；
- 写 Revision 与 Source；
- 处理被替代当前状态；
- 记录用户确认和时间；
- 将 Proposal 设为终态。

## 不变量

- 同一 Proposal 只能成功应用一次；
- 重复请求幂等；
- AI 不能调用绕过确认的写接口；
- 目标 Revision 已变化时返回冲突，不静默覆盖；
- rejected/deferred 不进入默认 Context；
- Fortune narrative 不能作为 confirmed fact 自动应用。

## 非目标

- 不实现 AI Proposal 生成；
- 不实现前端确认 UI；
- 不实现 Skill 自更新 Proposal；
- 不实现 Document 内容 Changeset 或 Agent 文档编辑；
- 不实现外部副作用写 Capability。

## 验收标准

- [ ] 所有状态转换强校验；
- [ ] 接受和 Wiki 更新事务一致；
- [ ] 修改后接受保留原建议与最终内容；
- [ ] 幂等、冲突和并发测试完整；
- [ ] 用户隔离和审计来源正确；
- [ ] 不存在 Agent 直写 confirmed Wiki 的路径；
- [ ] 失败不会留下半应用状态。

## Grok必须验证

```text
cd go-backend && go test ./...
```

必须包含真实 PostgreSQL 事务、重复接受、并发冲突和跨用户测试。

Task 进入 `ready` 时按当时 Migration 目录分配下一个序号，并把
`*_wiki_proposal.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

Codex 通过 API 验证接受、修改接受、暂缓、拒绝、重复提交、冲突和跨用户访问；
Browser UI 验收在 TASK-020。

## Handoff

写入 `collaboration/handoffs/TASK-018-round-1.md` 后停止。
