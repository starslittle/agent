---
id: TASK-006
title: 建立 P0 Runtime 故障注入与统一验收报告
status: draft
executor: grok
base_commit: pending
business_round: ROUND-01
depends_on:
  - TASK-005
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P0：自动技术验收"
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#8：自动验收矩阵"
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#11：Definition of Done"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/tests/**
  - backend/scripts/**
  - go-backend/internal/**/*_test.go
  - go-backend/scripts/**
  - frontend/src/**/*.test.*
  - scripts/**
  - docs/operations/**
  - docs/architecture/agent-runtime-migration-progress.md
  - collaboration/handoffs/TASK-006-*.md
forbidden_paths:
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - frontend/src/components/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
---

# TASK-006：P0 Runtime 自动验收

## 目标

把分散的单元、集成和进程故障测试组织成一套可重复执行、以 Product Run 为中心的
P0 验收矩阵和摘要报告。

## 交付内容

自动覆盖：

- Python 进程终止与 checkpoint 接管；
- Go/浏览器断开和 Re-attach；
- 失败、超时、取消后的会话解锁；
- `cancel_requested` 与晚到完成事件竞态；
- sequence 连续、重复幂等和缺口失败关闭；
- Product Run、Python execution、assistant message 终态一致；
- Trace/provenance 完整且脱敏；
- 跨用户 Run/Event/Message 访问拒绝；
- 实时、刷新和复制正文一致性所需的可自动部分。

输出单一机器可读结果和简短 Markdown 摘要，不保存 Secret、完整 Prompt、用户内容或
未脱敏日志。

## 实现约束

- 本Task以验证为主，不借机重构业务代码；
- 发现产品实现缺陷时 Handoff 标记失败并建议后续修复 Task；
- 真实 Provider 不是本地架构测试前提；
- 需要 Docker/PostgreSQL/Redis 的套件必须清楚声明环境要求。

## 验收标准

- [ ] 每个 P0 风险都有可定位测试；
- [ ] 一条命令或明确分层命令能生成统一摘要；
- [ ] 失败退出码非零；
- [ ] 报告区分 passed/failed/skipped/not-run；
- [ ] 跳过项有原因，不能当作通过；
- [ ] 产物不泄露敏感信息；
- [ ] 不修改禁止范围。

## Grok必须验证

执行当时仓库定义的完整 Python、Go、前端和容器门禁，并在 Handoff 中记录版本、
命令、结果和未运行原因。不得仅复制历史迁移报告。

## Codex验收与E2E

Codex 独立检查测试真实性，并使用 Browser / Computer Use 复验正常回答、刷新恢复、
取消、失败解锁和正文一致性。自动报告和真实 E2E 都通过后才接受。

## Handoff

写入 `collaboration/handoffs/TASK-006-round-1.md` 后停止。
