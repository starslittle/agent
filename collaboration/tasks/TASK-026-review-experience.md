---
id: TASK-026
title: 建立 Review Record 结果录入与复盘体验
status: draft
executor: grok
base_commit: pending
business_round: ROUND-05
depends_on:
  - TASK-020
  - TASK-022
  - TASK-025
source_todos:
  - "docs/product/web-mvp.md#10：决策与复盘"
  - "docs/product/future-product.md#14：决策与复盘"
  - "docs/architecture/unified-agent-skill-architecture.md#Phase-4：Decision与Review"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/reviews/**
  - go-backend/internal/decisions/**
  - go-backend/internal/wiki/**
  - go-backend/internal/context/**
  - go-backend/internal/agent/**
  - go-backend/internal/agentclient/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/review*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/platform/postgres/review_*.go
  - go-backend/internal/platform/postgres/*review*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_review_foundation.sql
  - backend/agent/skills/**
  - backend/agent/graph.py
  - backend/agent/application.py
  - backend/configs/skills.yaml
  - backend/tests/**
  - frontend/src/features/reviews/**
  - frontend/src/features/decisions/**
  - frontend/src/lib/review-api.ts
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-026-*.md
forbidden_paths:
  - backend/agent/workflows/research_v1/**
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/workflows/decision_v1/**
  - frontend/src/auth/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-026：Review 记录与体验

## 目标

保存 Decision 的实际行动和结果，触发 Review Skill，展示复盘并让用户确认产生的
Wiki/Rule Proposal；同时完成 TASK-025 unavailable Review Workflow 的跨服务接入和
受控启用。

## 交付内容

- Review Record 与 Decision 稳定关联；
- 用户录入实际行动、结果和时间；
- 触发 Review Run；
- Go 从用户拥有的 Decision、历史 Context Revision 和当前允许的 Wiki 组装强类型
  Review 输入，浏览器不能伪造这些历史依据；
- Review Manifest 只有在跨服务协议和服务端能力开关就绪后才标记 available；
- 展示 expected/actual、假设验证和 Lessons；
- Review Proposal 复用 TASK-018/020 确认机制；
- Decision 页面可查看历史 Review；
- 不修改原 Decision 的历史依据。

## 非目标

- 不实现提醒系统；
- 不实现跨多个 Decision 的人格画像；
- 不自动更新 Skill；
- 不自动接受规则变化。

## 验收标准

- [ ] 结果录入和 Review 状态机清楚；
- [ ] Review 与 Run、Decision、Context 可追溯；
- [ ] Review 启用前不可由 Root Assistant 选择，启用后显式和受控自动路由正确；
- [ ] 原 Decision 不被回写；
- [ ] Proposal 必须用户确认；
- [ ] 重复触发和并发有明确行为；
- [ ] 刷新后 Review 记录存在；
- [ ] 跨用户访问拒绝；
- [ ] 页面错误和空状态完整。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd backend && uvx ruff check agent tests
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

Task 进入 `ready` 时按当时 Migration 目录分配下一个序号，并把
`*_review_foundation.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

使用 Browser / Computer Use 打开已决定事项、录入结果、运行 Review、查看复盘、
确认/拒绝 Proposal，并确认历史 Decision 未变化。

## Handoff

写入 `collaboration/handoffs/TASK-026-round-1.md` 后停止。
