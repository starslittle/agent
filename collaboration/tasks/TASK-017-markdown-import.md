---
id: TASK-017
title: 建立单篇 Markdown 保存与导入
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-015
source_todos:
  - "docs/product/recruiting-mvp.md#8.2：Markdown Document"
  - "docs/product/recruiting-mvp.md#9：Memory Proposal"
  - "docs/product/web-mvp.md#9：Markdown与Obsidian"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: medium
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/documents/**
  - go-backend/internal/httpapi/document*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/platform/postgres/document_*.go
  - go-backend/internal/platform/postgres/*document*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_document_foundation.sql
  - frontend/src/features/documents/**
  - frontend/src/features/wiki/**
  - frontend/src/lib/document-api.ts
  - frontend/src/pages/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-017-*.md
forbidden_paths:
  - backend/**
  - frontend/src/components/chat/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-017：Markdown 导入

## 目标

支持用户导入一篇 UTF-8 Markdown，保存原文和来源元数据，并在 Wiki 中查看文档；
本Task不进行 AI 信息提取。

## 文档契约

至少记录：

- document ID、user ID；
- title；
- Markdown 正文或受控存储引用；
- source、original path/name；
- domain；
- content hash；
- size；
- created/updated 时间；
- extraction 状态。

执行前冻结原文存储决策。P0 可以在明确大小上限下保存 PostgreSQL 文本，但 API
必须保持未来迁移到对象存储的边界，不把本地绝对路径作为产品身份。

## 安全约束

- 只接受允许的文本类型和大小；
- 文件名不参与任意路径拼接；
- 不渲染危险 HTML/脚本；
- 重复导入通过 hash 给出可理解行为；
- 不把原文自动当成 confirmed fact；
- 用户只能访问自己的文档。

## 非目标

- 不批量导入；
- 不做 Obsidian 同步；
- 不做 AI 提取；
- 不实现 Agent 发起的 Document create/update/delete；该能力需要独立 Capability、
  Changeset、删除确认和审计 Task；
- 不提供 Agent 可调用的隐藏或恢复操作；
- 不直接生成 Wiki Item；
- 不处理任意 Office/PDF 格式。

## 验收标准

- [ ] 单篇上传、查看和删除/归档行为明确；
- [ ] 大小、编码、扩展名和危险内容校验；
- [ ] 原文刷新后保持；
- [ ] 重复导入行为稳定；
- [ ] 文档与 Wiki Item 事实分离；
- [ ] 用户隔离和 CSRF 正确；
- [ ] Migration 和存储测试通过。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

Task 进入 `ready` 时按当时 Migration 目录分配下一个序号，并把
`*_document_foundation.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

使用 Browser / Computer Use 上传一篇面试复盘 Markdown，验证原文、元数据、刷新、
重复导入、错误文件、危险内容和跨用户拒绝。

## Handoff

写入 `collaboration/handoffs/TASK-017-round-1.md` 后停止。
