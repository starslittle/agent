---
id: TASK-010
title: 建立 Root Skill Resolver
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-009
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#产品架构主线TODO2：Skill化专业能力"
  - "docs/architecture/unified-agent-skill-architecture.md#5：Root Assistant"
  - "docs/product/recruiting-mvp.md#5：Skill触发方式"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/root/**
  - backend/agent/application.py
  - backend/agent/graph.py
  - backend/agent/state.py
  - backend/agent/skills/**
  - backend/agent/prompts/skill_route_*.txt
  - backend/tests/unit/test_root_*.py
  - backend/tests/fixtures/skill_route_*.json
  - collaboration/handoffs/TASK-010-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/**
  - backend/agent/tools/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
---

# TASK-010：Root Skill Resolver

## 目标

让 Python Root Assistant 在统一请求入口中处理显式 Skill 和受控自动路由，选择
Direct Answer 或最多一个 available 主 Skill。

## 路由优先级

```text
显式 requested_skill
→ Skill 存在和 available 校验
→ 权限、模型能力、输入、风险、预算校验
→ 无显式 Skill 时结构化自动路由
→ 低置信度 Direct Answer
→ 中置信度返回 confirmation_required
→ 高置信度执行一个主 Skill
```

## 结果契约

至少输出：

```text
requested_skill
resolved_skills
primary_skill
confidence
selection_source
requires_confirmation
reason_code
```

对外只返回可公开原因码或摘要，不暴露模型隐藏思维过程。

## 安全与回退

- 显式 Skill 优先但不能绕过校验；
- Fortune 自动识别后必须先确认；
- 简单请求默认 Direct Answer，默认 0 工具调用；
- 未知/不可用 Skill 使用稳定错误；
- 路由模型失败时确定性回退；
- 一次 Run 最多选择一个主 Skill；Direct Answer 返回空 Skill 集合；
- 不允许模型自由创建 Workflow 或 Capability 名称。

MVP 的 `confirmation_required` 是无 Skill 副作用的完成结果，不新增暂停中的 Product
Run 状态。用户确认通过一个正常后续 Turn 显式选择该 Skill；前一 Run 不恢复、不
重复执行。Run 内持久暂停/恢复属于未来候选。

## 非目标

- 不修改现有 Workflow 行为；
- 不实现 Decision；
- 不修改前端；
- 不做多 Skill 编排；
- 不将 Direct Answer 注册为用户 Skill。

## 验收标准

- [ ] 显式选择、自动选择和回退均有测试；
- [ ] 置信度边界行为稳定；
- [ ] Fortune 确认策略不可绕过；
- [ ] `confirmation_required` Run 不执行目标 Skill、Capability 或产品写入；
- [ ] Skill/模型/Capability 校验复用现有 Registry；
- [ ] 路由结果进入 Runtime Event/provenance；
- [ ] 简单对话不默认联网；
- [ ] 不建立第二个 Root Graph；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests/unit/test_root_*.py -q
cd backend && uv run pytest tests/unit -q
cd backend && uvx ruff check agent/root agent/application.py agent/graph.py
```

## Codex验收与E2E

Codex 通过内部 API 验证 Direct、显式 Research/Fortune、自动 Research、Fortune
确认、未知 Skill、路由模型失败和无工具简单对话。UI 验收在 TASK-012 完成。

## Handoff

写入 `collaboration/handoffs/TASK-010-round-1.md` 后停止。
