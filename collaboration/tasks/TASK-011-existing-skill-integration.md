---
id: TASK-011
title: 将 Research 与 Fortune 接入 Skill Registry 和 Root Assistant
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-010
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P1：Research/Fortune迁为Skill"
  - "docs/architecture/unified-agent-skill-architecture.md#7：首批Skill"
  - "docs/product/recruiting-mvp.md#4：首批Skill"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/application.py
  - backend/agent/graph.py
  - backend/agent/state.py
  - backend/agent/skills/**
  - backend/agent/workflows/__init__.py
  - backend/configs/skills.yaml
  - backend/configs/agents.yaml
  - backend/tests/**
  - collaboration/handoffs/TASK-011-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/research_v1/graph.py
  - backend/agent/workflows/fortune_v1/graph.py
  - backend/agent/prompts/**
  - backend/agent/tools/**
  - docker-compose.yml
---

# TASK-011：Research/Fortune Skill 接入

## 目标

让 Research 和 Fortune 通过 Skill Registry 进入现有 `research_v1/fortune_v1`
Subworkflow，同时保留旧 Agent Alias 兼容。

## 实现约束

- 不重写两个 Workflow；
- 不复制 Capability 白名单和预算；
- Skill Manifest 是专业能力定义，AgentSpec 仅保留兼容期职责；
- Direct Answer 继续进入 `chat_v1`，不伪装成 Skill；
- Fortune 的出生信息提取、确定性排盘和解释分层保持不变；
- Research 的证据和 Citation 契约保持不变；
- 不允许 Skill 绕过 Runtime deadline、取消或 provenance。

## 非目标

- 不实现 Decision；
- 不优化 Research 0/1/N；
- 不增加 Fortune 知识库；
- 不修改前端；
- 不删除旧 Agent 数据列。

## 验收标准

- [ ] `requested_skill=research` 进入 `research_v1`；
- [ ] `requested_skill=fortune` 进入 `fortune_v1`；
- [ ] Direct Answer 进入 `chat_v1`；
- [ ] 旧 `research_agent/fortune_agent` 映射行为兼容；
- [ ] Run 记录 Skill、Workflow、Capability 和模型快照；
- [ ] Fortune 自动选择仍要求确认；
- [ ] Workflow 文件没有行为性重写；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd backend && uvx ruff check agent tests
```

至少覆盖显式、兼容 Alias、自动路由、不可用 Skill、Capability 校验和取消传播。

## Codex验收与E2E

Codex 使用 API 运行 Direct、Research 和 Fortune，检查 Runtime Event、Artifact、
Citation、Capability、终态和 provenance；确认三条路径共享一个 Root Assistant。

## Handoff

写入 `collaboration/handoffs/TASK-011-round-1.md` 后停止。
