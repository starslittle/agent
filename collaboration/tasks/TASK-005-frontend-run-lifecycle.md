---
id: TASK-005
title: 前端切换到 Create Attach Cancel 生命周期
status: draft
executor: grok
base_commit: pending
business_round: ROUND-01
depends_on:
  - TASK-004
source_todos:
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#7：前端改造"
  - "docs/architecture/unified-agent-skill-architecture.md#9：Run协议"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - frontend/src/lib/chat-api.ts
  - frontend/src/components/chat/**
  - frontend/src/hooks/**
  - frontend/src/pages/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-005-*.md
forbidden_paths:
  - go-backend/**
  - backend/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-005：前端 Run 生命周期迁移

## 目标

将聊天前端从单个 `POST /messages/stream` 切换为 Create → Attach/Re-attach →
Cancel，确保停止按钮、刷新恢复和终态完全以服务端 Product Run 为准。

## 当前事实

- 当前前端在 SSE `meta` 到达前拿不到 `run_id`；
- 本地 Abort 只能代表连接结束，不能代表后台取消；
- TASK-002～004 将提供结构化事件和独立 Run API。

## 交付内容

- Create 成功并获得 `run_id` 后才进入可取消状态；
- Attach 消费结构化事件；
- 记录最后确认 sequence，用于重新附着；
- 本地 Abort 只关闭订阅；
- Cancel 请求失败时保留运行状态并允许重试；
- 页面刷新后能恢复活动 Run；
- 服务端 `done` 是消息终态的唯一来源。

## 非目标

- 不删除“深度思考”开关，本项只改 Run 生命周期；
- 不增加 Skill UI；
- 不修改后端协议；
- 不用 localStorage 作为 Run 事实源。

## 验收标准

- [ ] 前端不再使用旧流接口创建新 Run；
- [ ] 停止按钮不会在缺少 `run_id` 时可用；
- [ ] 刷新和断线后可重新附着；
- [ ] Cancel 失败不会显示“已停止”；
- [ ] 终态后清理活动 Run 状态；
- [ ] 同一会话下一条消息可正常发送；
- [ ] Activity 与正文仍保持分离；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd frontend && npm run lint
cd frontend && npm run build
```

如已建立前端测试脚本，补充并运行 Run 状态机测试。

## Codex验收与E2E

使用 Browser / Computer Use 验证正常完成、生成中刷新、网络断开、停止成功、停止
失败重试、取消/完成竞态以及终态后的下一轮对话。

## Handoff

写入 `collaboration/handoffs/TASK-005-round-1.md` 后停止。
