---
id: TASK-004
title: 建立 Run Event Attach 与 Re-attach
status: draft
executor: grok
base_commit: pending
business_round: ROUND-01
depends_on:
  - TASK-003
source_todos:
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#5.2：订阅与重新附着"
  - "docs/architecture/agent-runtime-migration-progress.md#传输与产品Run"
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
  - collaboration/handoffs/TASK-004-*.md
forbidden_paths:
  - frontend/**
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-004：Run Event Attach / Re-attach

## 目标

提供按 Run ID 独立订阅和重新附着事件的接口，使浏览器刷新、网络断开和多次订阅
不改变 Run 语义。

## 输入与输出契约

目标接口：

```text
GET /api/v1/agent-runs/{run_id}/events?starting_after=N
```

要求：

- 事件 sequence 严格递增；
- `starting_after` 之后回放，不重复确认过的事件；
- 活动 Run 回放后继续实时订阅；
- 终态 Run 回放后返回唯一终态；
- 序号缺口无法追平时失败关闭；
- 浏览器断开只 detach，不发送取消。

## 实现约束

- Python Runtime Store 仍是 execution event outbox 的事实源；
- Go 保存产品所需的脱敏投影；
- 订阅者数量不决定 Run 是否继续；
- 跨用户读取必须拒绝；
- 不通过内存中单个 channel 假装支持重启恢复。
- 本 Task 不授权 Migration；若现有 Event/Product Run Schema 无法满足回放不变量，
  必须退回 `draft` 重新冻结数据库范围。

## 非目标

- 不切换前端调用；
- 不实现 Citation 业务元数据；
- 不改变 Workflow；
- 不执行生产 rollout。

## 验收标准

- [ ] 首次 Attach 和 `starting_after` 回放正确；
- [ ] 活动 Run 可在回放后继续实时接收；
- [ ] 多次 Attach 不重复持久化消息；
- [ ] 终态只出现一次；
- [ ] 浏览器断开不触发 Cancel；
- [ ] 缺口、上游失败和超时具有稳定错误；
- [ ] 用户隔离有自动测试；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
```

至少包含断开、重复订阅、序号缺口、终态回放和权限测试。

## Codex验收与E2E

Codex 通过 API 与浏览器验证：生成中断开、刷新后从最后 sequence 恢复、最终正文
不重复，另一个用户无法订阅该 Run。

## Handoff

写入 `collaboration/handoffs/TASK-004-round-1.md` 后停止。
