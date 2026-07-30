---
id: TASK-023
title: 建立 Decision 对话决策卡与保存体验
status: draft
executor: grok
base_commit: pending
business_round: ROUND-04
depends_on:
  - TASK-012
  - TASK-015
  - TASK-021
  - TASK-022
source_todos:
  - "docs/product/recruiting-mvp.md#4.1：决策Skill"
  - "docs/product/recruiting-mvp.md#7.1：对话页面"
  - "docs/product/recruiting-mvp.md#10：最小决策卡"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - frontend/src/features/decisions/**
  - frontend/src/components/chat/**
  - frontend/src/features/wiki/**
  - frontend/src/lib/decision-api.ts
  - frontend/src/**/*.test.*
  - go-backend/internal/httpapi/decision*.go
  - go-backend/internal/decisions/**
  - collaboration/handoffs/TASK-023-*.md
forbidden_paths:
  - backend/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-023：Decision 产品体验

## 目标

在统一对话中展示 Decision Skill 的结构化结果，让用户查看上下文、选项、未知项和
重新评估条件，并明确保存自己的最终选择。

## 交付内容

- 自动或 `/decision` 进入 Decision；
- 回答展示 Decision Skill 与选择来源；
- 可展开查看实际 Context；
- 选项、收益、代价、风险、反例和未知项结构化展示；
- 最小 Decision Card；
- 用户选择选项、填写原因并保存；
- 显示重新评估条件；
- 保存成功后可从 Wiki 页面中的关联决策区域查看 Decision Record；Decision 仍是
  独立产品对象，不伪装成 Wiki Item；
- 未做选择时保持 Draft。

## 非目标

- 不替用户推荐为自动最终选择；
- 不建设独立复杂决策中心；
- 不实现提醒；
- 不实现完整 Review；
- 不修改 Decision Workflow 或 Schema。

## 验收标准

- [ ] 自动和显式 Decision 入口可用；
- [ ] Context 引用可见且准确；
- [ ] 用户选择前保持 Draft；
- [ ] 保存选择后刷新仍存在；
- [ ] 修改 Wiki 不改变历史依据；
- [ ] 重复保存和冲突有明确反馈；
- [ ] Proposal 与 Decision 写入分开确认；
- [ ] 移动端和桌面端基本可用。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

## Codex验收与E2E

使用 Browser / Computer Use 完成自动 Decision、显式 `/decision`、查看 Context、
保存选择、刷新、修改 Wiki 后查看历史以及未选择 Draft。

## Handoff

写入 `collaboration/handoffs/TASK-023-round-1.md` 后停止。
