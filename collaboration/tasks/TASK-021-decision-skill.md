---
id: TASK-021
title: 建立 Decision Skill 与强类型决策结果
status: draft
executor: grok
base_commit: pending
business_round: ROUND-04
depends_on:
  - TASK-011
  - TASK-016
  - TASK-020
source_todos:
  - "docs/product/recruiting-mvp.md#4.1：决策Skill"
  - "docs/product/recruiting-mvp.md#10：最小决策卡"
  - "docs/architecture/unified-agent-skill-architecture.md#7.1：Decision"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/skills/**
  - backend/agent/workflows/decision_v1/**
  - backend/agent/prompts/decision_*.txt
  - backend/agent/state.py
  - backend/agent/graph.py
  - backend/agent/application.py
  - backend/configs/skills.yaml
  - backend/tests/**
  - collaboration/handoffs/TASK-021-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/research_v1/**
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/tools/**
  - docker-compose.yml
---

# TASK-021：Decision Skill

## 目标

新增 `decision_v1` 受控 Workflow 和 available Decision Manifest，使用 Context
Package 输出强类型决策分析、Decision Draft 和可选 Wiki Proposal，不替用户做出
最终选择。

## 输入

- 用户问题；
- 本次 Context Package；
- 用户明确的选项（如有）；
- 目的、限制和 deadline；
- 是否允许提出 Wiki Proposal。

## 输出

至少包含：

- problem；
- used_context_refs；
- options；
- 每个选项的收益、代价和风险；
- counterarguments；
- unknowns；
- assumptions；
- reevaluation_conditions；
- neutral analysis；
- Decision Draft；
- optional Wiki Proposal；
- uncertainty 与安全说明。

## 实现约束

- 不替用户自动选择；
- 不把 AI 分析写成用户事实；
- 上下文引用必须对应实际 Item/Revision；
- 不使用未确认或被遗忘信息；
- 输出强类型校验和有界修复；
- 默认不调用外部工具，只有 Manifest 明确允许时才可使用；
- 当前 MVP 不调用 Research Skill、不生成多 Skill ExecutionPlan；相关组合能力保留
  在未来候选文档；
- Wiki Proposal 复用 TASK-019/020 已建立的结构化事件、持久化和确认通道，不新增
  Python 直写 Go 产品表的路径；
- 失败不产生已确认 Decision 或 Wiki 写入。

## 非目标

- 不实现 Review；
- 不实现提醒和任务管理；
- 不实现复杂决策评分算法；
- 不修改 Research/Fortune；
- 不实现前端和持久化。

## 验收标准

- [ ] Decision Manifest 启动校验；
- [ ] `requested_skill=decision` 进入 `decision_v1`；
- [ ] 强类型成功/修复/失败路径完整；
- [ ] 实际上下文引用准确；
- [ ] 无上下文时可明确退化；
- [ ] 不生成自动最终选择；
- [ ] Proposal 只进入待确认通道；
- [ ] Run provenance 完整。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd backend && uvx ruff check agent tests
```

使用确定性 fake model 覆盖成功、未知项、缺上下文、非法输出和取消。

## Codex验收与E2E

Codex 通过 API 提交秋招决策问题，检查 Skill 选择、Context 引用、选项分析、未知项、
重新评估条件、Proposal 和无自动选择。Browser 体验在 TASK-023。

## Handoff

写入 `collaboration/handoffs/TASK-021-round-1.md` 后停止。
