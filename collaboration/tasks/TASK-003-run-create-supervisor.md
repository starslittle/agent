---
id: TASK-003
title: 分离 Create Run 并建立 Go Run Supervisor
status: draft
executor: grok
base_commit: pending
business_round: ROUND-01
depends_on:
  - TASK-002
source_todos:
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#4.1：创建Run与订阅事件分离"
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#4.2：Go Run Supervisor拥有产品执行"
  - "docs/architecture/unified-agent-skill-architecture.md#9：Run协议"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/conversation/**
  - go-backend/internal/runs/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/agent/**
  - go-backend/internal/agentclient/**
  - go-backend/internal/platform/postgres/**
  - go-backend/cmd/server/**
  - collaboration/handoffs/TASK-003-*.md
forbidden_paths:
  - frontend/**
  - backend/agent/**
  - backend/app/runtime/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-003：Create Run 与 Go Run Supervisor

## 目标

新增独立 Create Run API，使 Product Run 在返回 `run_id` 后由 Go Supervisor
后台启动或恢复，不再由浏览器 SSE Handler 拥有生命周期。

## 历史TODO追溯

部分承接 Create/Attach/Cancel 分离和 Go Run Supervisor。本Task完成创建与后台
所有权；事件 Attach 由 TASK-004，前端切换由 TASK-005。

## 输入与输出契约

目标接口：

```text
POST /api/v1/conversations/{conversation_id}/runs
```

事务内创建：

- user message；
- pending/streaming assistant message；
- Product Run；
- execution identity 与 idempotency key。

成功后立即返回：

- `run_id`；
- `execution_id`；
- user/assistant message ID；
- 初始状态；
- 事件协议版本。

## 实现约束

- Supervisor 不执行模型、工具或 LangGraph 节点；
- 浏览器请求取消不能终止 Supervisor；
- 同一会话仍保持单活动 Run 约束；
- 创建重试按 `client_message_id/idempotency_key` 幂等；
- 旧 `/messages/stream` 在兼容期保留；
- 多 Gateway owner 问题必须使用数据库 claim/lease 或明确保持单 owner 门禁，
  不能用未说明的进程内 map 冒充分布式所有权。
- 本 Task 不授权 Migration；若当前 Product Run Schema 无法实现恢复和 claim
  不变量，必须退回 `draft` 重新冻结数据库范围。

## 非目标

- 不实现浏览器 Attach；
- 不切换前端；
- 不修改 Python Workflow；
- 不进行生产默认切换。

## 验收标准

- [ ] Create API 在启动流之前返回稳定 Run 身份；
- [ ] 创建消息和 Run 具有事务一致性；
- [ ] Supervisor 独立于 HTTP 连接运行；
- [ ] 重复创建不产生重复消息或 Run；
- [ ] Go 重启后会扫描活动 Run，并通过状态对账或恢复进入唯一明确终态；
- [ ] Go 重启恢复和重复 Supervisor claim 有自动测试；
- [ ] 旧入口继续兼容；
- [ ] 跨用户和 CSRF 权限正确；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
```

需要真实 PostgreSQL 的测试必须在 Handoff 中区分“已运行”和“环境缺失”。

## Codex验收与E2E

Codex 检查 Create API、数据库事务和旧路径回归，并在可运行环境验证浏览器断开后
后台 Run 不因连接消失而被语义取消。

## Handoff

写入 `collaboration/handoffs/TASK-003-round-1.md` 后停止。
