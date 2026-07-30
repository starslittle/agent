---
id: TASK-013
title: 建立 Agent Runs 最小可观察页面
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-009
  - TASK-012
source_todos:
  - "docs/product/recruiting-mvp.md#7.3：Agent Runs"
  - "docs/product/recruiting-mvp.md#11：Agent Run"
  - "docs/architecture/agent-runtime.md#14：Event Trace与Usage"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: medium
review_gate: required
codex_e2e: required
allowed_paths:
  - frontend/src/features/runs/**
  - frontend/src/pages/**
  - frontend/src/lib/run-api.ts
  - frontend/src/App.tsx
  - frontend/src/App.css
  - frontend/src/components/chat/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-013-*.md
forbidden_paths:
  - backend/**
  - go-backend/**
  - frontend/src/auth/**
  - docker-compose.yml
---

# TASK-013：Agent Runs 页面

## 目标

基于现有 Run 列表和详情 API，提供最小 Agent Runs 页面，展示真实系统动作、状态和
错误，不展示模型隐藏思维过程。本 Task 只交付普通用户查看自己 Run 的视图；内部
跨用户观测由 TASK-028 在同一套页面组件和查询模型上扩展。

## 页面内容

- Run ID、会话、时间与终态；
- requested/resolved Skill 和实际 Workflow；
- Model ID/Profile/实际模型；
- Capability/Tool 与状态；
- Activity 时间线；
- Artifact/Citation 引用；
- Token、模型调用数、工具调用数和耗时；
- 取消、超时和失败原因；
- provenance 版本摘要。

敏感字段使用服务端脱敏结果，前端不尝试展示完整 Prompt 或工具输入。

## 非目标

- 不修改 Run API；
- 不增加管理员角色或跨用户查询；
- 不建设运维级 Trace 系统；
- 不展示 Chain of Thought；
- 不增加任意重放或生产控制按钮。

## 验收标准

- [ ] 列表分页和状态筛选可用；
- [ ] 详情时间线按 sequence/时间稳定排序；
- [ ] 运行中、完成、取消、失败、超时均有明确表达；
- [ ] 空状态、加载和错误状态完整；
- [ ] 不泄露 Prompt、Secret 或完整敏感内容；
- [ ] 从聊天可导航到关联 Run；
- [ ] 刷新后仍能查看历史 Run。

## Grok必须验证

```text
cd frontend && npm run lint
cd frontend && npm run build
```

补充状态映射和空/失败数据的组件测试或 fixture。

## Codex验收与E2E

使用 Browser / Computer Use 产生完成、取消和失败 Run，逐一检查列表、详情、时间线、
Token/耗时、错误展示和聊天跳转。

## Handoff

写入 `collaboration/handoffs/TASK-013-round-1.md` 后停止。
