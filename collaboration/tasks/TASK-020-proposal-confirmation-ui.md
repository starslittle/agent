---
id: TASK-020
title: 建立 Proposal 接受修改暂缓拒绝体验
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-015
  - TASK-018
  - TASK-019
source_todos:
  - "docs/product/recruiting-mvp.md#9：Memory Proposal"
  - "docs/product/recruiting-mvp.md#7.1-7.2：对话与Wiki确认入口"
  - "docs/product/web-mvp.md#11：进化收件箱"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/httpapi/proposal*.go
  - go-backend/internal/proposals/**
  - frontend/src/features/proposals/**
  - frontend/src/features/wiki/**
  - frontend/src/components/chat/**
  - frontend/src/lib/proposal-api.ts
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-020-*.md
forbidden_paths:
  - backend/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-020：Proposal 用户确认

## 目标

在对话结果和 Wiki 待确认区域展示 Proposal，让用户接受、修改后接受、暂缓或拒绝，
并清楚看到写入结果和来源。

## 交互要求

- 展示类型、原内容、新内容、来源、置信度和冲突；
- 接受前可展开查看关联文档/Run；
- 修改后接受保留原建议；
- 暂缓项可稍后处理；
- 拒绝项不进入默认上下文；
- 成功后刷新 Wiki 和 Proposal 状态；
- 冲突、重复提交和网络失败有可恢复反馈。

## 非目标

- 不建设独立“进化收件箱”一级页面；
- 不实现 Skill 改进 Proposal；
- 不增加自动批量接受；
- 不允许 Agent 自动点击确认。

## 验收标准

- [ ] 四种用户操作完整；
- [ ] 接受后 Wiki/Revision/Source 正确；
- [ ] 修改接受保留审计；
- [ ] 暂缓和拒绝不影响默认 Context；
- [ ] 重复点击和竞态幂等；
- [ ] 冲突不会静默覆盖；
- [ ] 页面刷新后状态一致；
- [ ] 对话与 Wiki 两处展示一致。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

## Codex验收与E2E

使用 Browser / Computer Use 分别执行接受、修改接受、暂缓、拒绝、重复点击、冲突和
失败重试；确认只有明确接受会改变 Wiki。

## Handoff

写入 `collaboration/handoffs/TASK-020-round-1.md` 后停止。
