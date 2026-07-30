---
id: TASK-008
title: 建立稳定 Model Catalog 与 model_id
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-001
  - TASK-006
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P1：Model Catalog与稳定model_id"
  - "docs/architecture/agent-runtime-migration-progress.md#产品架构主线TODO1：单一助手模式与模型选择"
  - "docs/architecture/agent-runtime.md#9：Model Gateway"
risk: medium
review_gate: required
codex_e2e: not_applicable
allowed_paths:
  - backend/agent/models/**
  - backend/agent/readiness.py
  - backend/configs/models.yaml
  - backend/tests/unit/test_model_*.py
  - backend/tests/fixtures/model_*.json
  - collaboration/handoffs/TASK-008-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-008：Model Catalog

## 目标

在现有 Model Gateway 之上增加稳定、强类型的产品 `model_id` 解析，使请求不再直接
携带 Provider、base URL、内部 Profile 或任意参数。

## 历史TODO追溯

部分承接 Model Catalog 和稳定 `model_id`。本Task建立 Python 权威解析与启动校验；
Go/Python Run 协议和持久化由 TASK-009 完成，模型选择器 UI 不在当前范围。

## 交付内容

第一版至少支持：

```text
model_id = auto
```

Catalog 解析为受控：

- Provider；
- Model Profile；
- 实际模型；
- streaming/tool calling/structured output 能力；
- 参数与限制；
- provenance fingerprint。

## 实现约束

- 不在 Catalog 保存 Secret；
- 不允许请求传入任意 Provider 参数；
- Workflow 仍只依赖 Model Gateway；
- 节点不能创建 Provider Client；
- Catalog 配置启动时强校验；
- `auto` 的解析策略确定、可测试并可封存快照。

## 验收标准

- [ ] `auto` 可稳定解析；
- [ ] 未知 `model_id` 使用稳定错误；
- [ ] 能力、Profile 和 Provider 引用校验；
- [ ] fingerprint 稳定；
- [ ] 配置未知字段失败；
- [ ] Secret 不进入配置、日志或 fingerprint；
- [ ] 现有 Model Gateway 测试不回归；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests/unit/test_model_*.py -q
cd backend && uv run pytest tests/unit -q
cd backend && uvx ruff check agent/models agent/readiness.py tests/unit/test_model_*.py
```

## Codex验收与E2E

本Task尚未进入产品请求链，`codex_e2e: not_applicable`。Codex 独立审查配置边界、
Secret 隔离、稳定 fingerprint 和与现有 Gateway 的唯一性。

## Handoff

写入 `collaboration/handoffs/TASK-008-round-1.md` 后停止。
