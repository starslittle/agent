---
id: TASK-012
title: 建立统一助手前端与 Skill 交互
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-007
  - TASK-011
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#产品架构主线TODO1：移除普通/深度思考Agent选择"
  - "docs/architecture/agent-runtime-migration-progress.md#P1：Skill快捷按钮与composer chip"
  - "docs/product/recruiting-mvp.md#5-7：Skill触发、可见性与对话页面"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - frontend/src/components/chat/**
  - frontend/src/features/skills/**
  - frontend/src/features/runs/**
  - frontend/src/lib/chat-api.ts
  - frontend/src/hooks/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-012-*.md
forbidden_paths:
  - backend/**
  - go-backend/**
  - frontend/src/auth/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
---

# TASK-012：统一助手前端

## 目标

删除面向用户的永久“深度思考”Agent 模式，将聊天入口收敛为一个启点助手，并支持
显式 Skill、自动选择结果、确认和结构化活动展示。

## 交付内容

- 删除“深度思考”开关和 `deep -> research_agent` 映射；
- 新请求使用 `model_id=auto` 和可选 `requested_skill`；
- `/` 菜单只展示当前 available 且 UI visible 的 Skill；
- ROUND-02 必须支持 `/fortune`；`/decision` 在 TASK-021 将 Decision 标记
  available 后由同一动态菜单自动出现，TASK-012 不提前伪造入口；
- 显式选择以可移除 Skill Chip 展示；
- 回答顶部展示实际 Skill、自动/用户指定/兼容来源；
- 中置信度或 Fortune 自动选择显示确认交互；
- 确认操作创建一个正常后续 Turn，并以显式 `requested_skill` 执行；不假装恢复
  前一个已经完成的 Run；
- Activity、Citation、Artifact 与回答正文分层。

## 非目标

- 不增加模型选择器；
- 不建设 Skills 独立页面；
- 不实现 Wiki 或 Decision 业务；
- 不保留“普通/深度思考”作为换名后的永久按钮；
- 不修改后端协议。

## 验收标准

- [ ] 前端不再提交 `agent_name`；
- [ ] 普通输入默认无显式 Skill；
- [ ] Slash 与 Chip 只对 available Skill 正确设置/清除 requested Skill；
- [ ] 自动路由结果可见；
- [ ] 确认前不会执行需确认 Skill；
- [ ] Activity 不进入回答正文；
- [ ] 移动端和桌面端基础交互可用；
- [ ] 现有会话、取消和恢复不回归。

## Grok必须验证

```text
cd frontend && npm run lint
cd frontend && npm run build
```

执行前复核测试脚本并补充 Slash、Chip、确认和路由结果的状态测试。

## Codex验收与E2E

使用 Browser / Computer Use 验证普通对话、显式 Fortune、自动 Research、Fortune
确认后的新 Turn、移除 Chip、取消/刷新恢复和旧会话显示。确认用户始终感知为同一个
助手，并且 ROUND-02 不出现尚不可用的 Decision 入口。

## Handoff

写入 `collaboration/handoffs/TASK-012-round-1.md` 后停止。
