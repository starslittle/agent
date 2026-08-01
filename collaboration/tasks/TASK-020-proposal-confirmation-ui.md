---
id: TASK-020
title: 建立文档 Proposal 接受修改暂缓拒绝体验
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
  - "docs/product/recruiting-mvp.md#7.1-7.2：对话与我的空间确认入口"
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
  - frontend/src/features/space/**
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

在对话结果、文档详情和“关联上下文”待确认区域展示 Proposal，让用户接受、修改后接受、
暂缓或拒绝，并清楚看到写入结果、Document Revision 来源和对未来 Context 的影响。

## 信息架构

- 文档详情显示当前文档产生的待确认项与历史处理结果；
- 对话结果显示本次 Run 产生的 Proposal；
- 结构化信息详情可以回到来源 Document/Revision；
- 本轮不建设独立“进化收件箱”一级页面，也不把 Proposal 平铺到空间根目录。

## 交互要求

- 展示类型、原内容、新内容、来源片段、Document Revision、置信度和冲突；
- 接受前可展开查看关联文档与 Run；
- 修改后接受保留原建议与最终内容；
- 暂缓项可稍后从原文档或上下文入口处理；
- 拒绝项不进入默认 Context；
- 成功后刷新关联上下文和 Proposal 状态，不修改 Markdown 原文；
- 冲突、重复提交和网络失败有可恢复反馈，异步状态通过 `aria-live` 公告；
- 所有确认动作使用语义按钮、可见焦点和明确文案，Agent 不能代替用户点击。

## 非目标

- 不建设独立进化收件箱一级页面；
- 不实现 Skill 改进 Proposal；
- 不增加自动批量接受；
- 不实现 Document Changeset 或覆盖导入；
- 不允许 Agent 自动确认。

## 验收标准

- [ ] 四种用户操作完整；
- [ ] 接受后 Wiki/Revision/Source 正确并关联 Document Revision；
- [ ] 修改接受保留审计；
- [ ] 暂缓和拒绝不影响默认 Context；
- [ ] 重复点击和竞态幂等；
- [ ] 冲突不会静默覆盖；
- [ ] 页面刷新后状态一致；
- [ ] 对话、文档详情和上下文详情的数据语义一致；
- [ ] 接受 Proposal 不修改 Markdown 原文；
- [ ] 键盘、移动端、焦点和错误恢复可用。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

## Codex验收与E2E

使用 Browser / Computer Use 分别执行接受、修改接受、暂缓、拒绝、重复点击、冲突和
失败重试；从 Proposal 往返 Document Revision 与 Run，确认只有明确接受会改变结构化
上下文，且原 Markdown 不被改写。

## Handoff

写入 `collaboration/handoffs/TASK-020-round-1.md` 后停止。
