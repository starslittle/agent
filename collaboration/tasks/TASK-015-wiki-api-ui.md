---
id: TASK-015
title: 建立 Wiki CRUD API 与最小页面
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-014
source_todos:
  - "docs/product/recruiting-mvp.md#7.2：我的Wiki"
  - "docs/product/recruiting-mvp.md#8.1：Wiki Item"
  - "docs/product/web-mvp.md#8：我的Wiki"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/httpapi/wiki*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/httpapi/*wiki*_test.go
  - frontend/src/features/wiki/**
  - frontend/src/pages/**
  - frontend/src/lib/wiki-api.ts
  - frontend/src/App.tsx
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-015-*.md
forbidden_paths:
  - backend/**
  - go-backend/internal/platform/postgres/migrations/**
  - frontend/src/components/chat/**
  - docker-compose.yml
---

# TASK-015：Wiki API 与页面

## 目标

让用户能够在 Web 中新增、浏览、搜索、修改、标记过期、暂时遗忘、恢复和永久删除
自己的最小 Wiki 信息，并查看类型、状态、来源和历史。

## API能力

- 创建用户直接输入的 Wiki Item；
- 列表、分页、类型/状态/领域筛选和简单搜索；
- 查看当前 Revision 与来源；
- 修改并生成新 Revision；
- 标记 outdated 或 forgotten；
- 从已遗忘列表恢复到遗忘前状态；
- 永久删除当前 Wiki 对象，并返回不可恢复的明确结果；
- 明确的并发版本冲突；
- CSRF、认证和用户隔离。

## 页面能力

- Wiki 列表和筛选；
- 新增/编辑；
- 类型、状态、来源、更新时间；
- 查看历史；
- 过期、暂时遗忘、恢复和永久删除确认；
- 加载、空状态、错误和冲突提示。

页面必须提供独立的“暂时遗忘”和“永久删除”操作：

- 暂时遗忘明确说明可恢复，并提供“已遗忘”筛选和恢复入口；
- 永久删除必须二次确认，明确不可恢复及只删除当前 Wiki 对象、不自动删除独立
  Conversation、Run、Decision 或原始 Document；
- 两种操作都不能由 Agent 自动触发。

## 非目标

- 不实现 AI 自动提取；
- 不实现向量检索；
- 不实现批量导入；
- 不实现 Proposal；
- 不实现复杂领域专属表单。

## 验收标准

- [ ] CRUD 与状态变化遵守 TASK-014 不变量；
- [ ] 用户只能访问自己的数据；
- [ ] 刷新后数据和历史存在；
- [ ] 冲突不会静默覆盖；
- [ ] forgotten 默认不在活动列表；
- [ ] 已遗忘列表可查看并恢复，恢复后回到遗忘前状态；
- [ ] 永久删除后正文、历史正文和来源正文不可再读取或恢复；
- [ ] Agent/API 内部身份无法调用遗忘、恢复和永久删除用户操作；
- [ ] UI 不把 AI analysis 显示为 confirmed fact；
- [ ] 空、错、加载和移动端基本可用；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

## Codex验收与E2E

使用 Browser / Computer Use 完成新增、编辑、冲突、过期、暂时遗忘、恢复、永久
删除、历史查看、刷新和跨用户拒绝；确认永久删除不可恢复且页面准确说明删除范围。

## Handoff

写入 `collaboration/handoffs/TASK-015-round-1.md` 后停止。
