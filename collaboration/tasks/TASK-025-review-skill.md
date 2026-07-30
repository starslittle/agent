---
id: TASK-025
title: 建立 Review Skill 与复盘 Proposal
status: draft
executor: grok
base_commit: pending
business_round: ROUND-05
depends_on:
  - TASK-024
source_todos:
  - "docs/product/web-mvp.md#10：决策与复盘"
  - "docs/architecture/unified-agent-skill-architecture.md#7：后续Review Skill"
  - "docs/architecture/unified-agent-skill-architecture.md#Phase-4：Decision与Review"
risk: medium
review_gate: required
codex_e2e: not_applicable
allowed_paths:
  - backend/agent/skills/**
  - backend/agent/workflows/review_v1/**
  - backend/agent/prompts/review_*.txt
  - backend/configs/skills.yaml
  - backend/tests/**
  - collaboration/handoffs/TASK-025-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/research_v1/**
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/workflows/decision_v1/**
  - docker-compose.yml
---

# TASK-025：Review Skill

## 目标

新增尚未对用户开放的受控 Review Workflow 和 unavailable Manifest，对照历史
Decision、当时 Context、用户实际行动和真实结果形成复盘分析与 Wiki Proposal。
TASK-026 完成产品存储、跨服务输入和页面接入后才能将其标记 available。

## 输入与输出

输入：

- Decision Record；
- 当时的 Context Revision；
- 用户补充的实际行动和结果；
- 当前相关事实；
- Review 目的。

输出：

- expected vs actual；
- assumption outcomes；
- what worked/failed；
- new evidence；
- lessons；
- reevaluation；
- Review Draft；
- optional Wiki/Rule Proposal。

## 实现约束

- 不重写历史 Decision；
- 不把结果反向伪造成当时已知事实；
- Proposal 仍需用户确认；
- 不用单次结果自动形成永久人格标签；
- 不替用户评价人生价值；
- 使用强类型输出和稳定 provenance。

## 非目标

- 不实现提醒；
- 不实现前端和产品存储；
- 不接入 Root Assistant 的用户可执行路由；
- 不自动修改 Skill；
- 不进行多 Decision 聚合画像。

## 验收标准

- [ ] Review Manifest/Workflow 可加载，且 Manifest 保持 `available=false`；
- [ ] 历史与当前信息清楚分层；
- [ ] 结果和假设逐项可追溯；
- [ ] Proposal 不直接写 Wiki；
- [ ] 取消、失败和非法输出安全；
- [ ] Decision 原记录不被修改；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd backend && uvx ruff check agent tests
```

## Codex验收与E2E

本 Task 尚未具备 Go 产品输入和用户入口，`codex_e2e: not_applicable`。Codex 独立
审查 Workflow、强类型契约、历史/当前信息分层、Proposal 输出和确定性测试；
真实 API 与页面 E2E 统一在 TASK-026 完成。

## Handoff

写入 `collaboration/handoffs/TASK-025-round-1.md` 后停止。
