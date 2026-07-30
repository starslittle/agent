---
id: TASK-022
title: 建立最小 Decision Record 与历史依据持久化
status: draft
executor: grok
base_commit: pending
business_round: ROUND-04
depends_on:
  - TASK-014
  - TASK-016
  - TASK-021
source_todos:
  - "docs/product/recruiting-mvp.md#10：最小决策卡"
  - "docs/product/web-mvp.md#10：决策与复盘"
  - "docs/architecture/unified-agent-skill-architecture.md#11：产品数据"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/decisions/**
  - go-backend/internal/httpapi/decision*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/platform/postgres/decision_*.go
  - go-backend/internal/platform/postgres/*decision*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_decision_foundation.sql
  - go-backend/internal/conversation/**
  - go-backend/internal/agent/**
  - collaboration/handoffs/TASK-022-*.md
forbidden_paths:
  - frontend/**
  - backend/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-022：Decision 持久化

## 目标

由 Go 保存最小 Decision Record、选项、假设、上下文历史引用、用户最终选择和重新
评估条件，使后续 Wiki 更新不会改变当时的决策依据。

## 数据模型

至少记录：

- decision ID、user ID、conversation/run ID；
- problem；
- Decision Skill/version/model provenance；
- Context Package 与 Item/Revision 引用；
- options、benefits、costs、risks；
- assumptions、unknowns、reevaluation conditions；
- AI analysis；
- user choice 和 choice reason；
- status、created/decided/reviewed 时间；
- later outcome/review 预留关联。

## 不变量

- 用户选择只能由用户操作保存；
- 历史 Context Revision 不随 Wiki 当前值变化；
- 重复保存幂等；
- Decision Draft 与最终选择分离；
- 跨用户访问拒绝；
- 删除/遗忘策略不伪造历史，但默认展示遵守隐私规则。
- Decision Draft 只能从服务端验证过的结构化 Skill Result/Artifact 投影，不信任
  浏览器提交的模型输出、provenance 或 Context 引用。

## 非目标

- 不实现完整 Review；
- 不实现提醒；
- 不实现前端；
- 不自动替用户选择；
- 不修改 Python Workflow。

## 验收标准

- [ ] Migration 和 Store/Service 测试完整；
- [ ] Draft、用户选择和状态转换清楚；
- [ ] 历史上下文引用不可漂移；
- [ ] 幂等、并发和权限正确；
- [ ] API 能保存和读取最小决策卡；
- [ ] 未选择状态不会伪装为已决定；
- [ ] provenance 可追溯；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
```

包含真实 PostgreSQL Migration、历史 Revision、重复选择和跨用户测试。

Task 进入 `ready` 时按当时 Migration 目录分配下一个序号，并把
`*_decision_foundation.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

Codex 通过 API 保存 Draft 和用户选择，随后修改 Wiki，确认历史决策仍引用当时
Revision；验证幂等、冲突和权限。UI 验收在 TASK-023。

## Handoff

写入 `collaboration/handoffs/TASK-022-round-1.md` 后停止。
