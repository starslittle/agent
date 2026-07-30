---
id: TASK-009
title: 建立 model_id 与 requested resolved Skill 跨服务 Run 协议
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-001
  - TASK-006
  - TASK-008
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P1：Model Catalog、Skill Registry与Run契约"
  - "docs/architecture/unified-agent-skill-architecture.md#9：Run协议"
  - "docs/architecture/unified-agent-skill-architecture.md#12：状态所有权"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/app/runtime/**
  - backend/app/api/agent_runs.py
  - backend/agent/application.py
  - backend/agent/state.py
  - backend/agent/specs.py
  - backend/agent/skills/**
  - backend/tests/**
  - go-backend/internal/agent/**
  - go-backend/internal/agentclient/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/platform/postgres/conversation_store.go
  - go-backend/internal/platform/postgres/*conversation*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_skill_run_protocol.sql
  - frontend/src/lib/chat-api.ts
  - collaboration/handoffs/TASK-009-*.md
forbidden_paths:
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - frontend/src/components/**
  - frontend/src/pages/**
  - go-backend/internal/platform/postgres/migrations/001_auth_foundation.sql
  - go-backend/internal/platform/postgres/migrations/002_conversation_foundation.sql
  - go-backend/internal/platform/postgres/migrations/003_agent_protocol_v1.sql
  - go-backend/internal/platform/postgres/migrations/004_agent_observability.sql
  - go-backend/internal/platform/postgres/migrations/005_agent_runtime_foundation.sql
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-009：Skill Run 跨服务协议

## 目标

在 Create Run、Go Product Run、Python AgentRunRequest、Runtime Event 和 provenance
中建立稳定 `model_id/requested_skill/resolved_skills` 契约，同时保持旧
`agent_name` 请求与数据兼容。

## 请求契约

新请求逐步采用：

```json
{
  "content": "用户请求",
  "client_message_id": "uuid",
  "model_id": "auto",
  "requested_skill": null
}
```

Run 至少记录：

- `model_id`；
- `requested_skill`；
- `resolved_skills`；
- `primary_skill`；
- `selection_source`；
- Skill/Workflow 版本；
- 模型与 Capability 快照；
- nullable `context_package_id`。

MVP 中 `resolved_skills` 的长度只能是 `0` 或 `1`：

```text
Direct Answer
→ resolved_skills = []
→ primary_skill = null

Skill
→ resolved_skills = [primary_skill]
```

复数字段只为协议兼容和未来演进预留，不表示当前已经支持多 Skill。

## 兼容规则

```text
default_llm_agent -> requested_skill = null
research_agent    -> requested_skill = research
fortune_agent     -> requested_skill = fortune
```

旧字段可以保留读取，但兼容映射必须集中在 Adapter；新前端和新产品实体不继续扩散
Agent 模式。

## 非目标

- 不实现自然语言自动路由；
- 不删除旧列或历史数据；
- 不切换统一助手 UI；
- 不实现 Decision；
- 不开放模型选择器。

## 验收标准

- [ ] Go/Python/Browser 类型和 JSON 契约一致；
- [ ] 新字段具有长度、枚举和未知值校验；
- [ ] compatibility mapping 单一且可测试；
- [ ] 创建时字段不可被重连改写，解析阶段字段只能由同一执行按 compare-and-set
  语义写入一次；
- [ ] resolved Skill 可由稳定事件写入 Product Run，重复事件幂等且冲突值失败关闭；
- [ ] Direct Answer 明确持久化空 Skill 集合和 nullable primary Skill；
- [ ] 旧客户端和旧记录继续可用；
- [ ] 跨用户权限不回归；
- [ ] Migration 可向前执行且不破坏已有数据。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

补充 Go/Python 协议 fixture 和 Migration 测试。

Task 进入 `ready` 时必须按当时 Migration 目录分配下一个序号，并把
`*_skill_run_protocol.sql` 收窄为唯一文件名；禁止改写已有 Migration。

## Codex验收与E2E

Codex 验证旧 `agent_name`、新 `requested_skill`、未知 Skill、未知 model、重连和历史
Run 读取；确认数据库与 provenance 快照一致。

## Handoff

写入 `collaboration/handoffs/TASK-009-round-1.md` 后停止。
