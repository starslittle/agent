---
id: TASK-002
title: 建立结构化 Browser Event 并分离 Activity 与回答正文
status: ready
executor: grok
base_commit: 634d90877e2176c6c15e80ccae2ad5ee22f5387f
business_round: ROUND-01
depends_on: []
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P0：运行事件与最终正文分离"
  - "docs/architecture/agent-runtime-p0-stabilization-plan.md#4.3：结构化事件端到端保真"
  - "docs/architecture/unified-agent-skill-architecture.md#10：浏览器事件"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/agent/**
  - go-backend/internal/agenttrace/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/platform/postgres/**
  - frontend/package.json
  - frontend/package-lock.json
  - frontend/src/lib/chat-api.ts
  - frontend/src/lib/conversation-stream-reducer.ts
  - frontend/src/components/chat/**
  - frontend/src/hooks/**
  - frontend/src/**/*.test.*
  - docs/architecture/agent-runtime-migration-progress.md
  - collaboration/handoffs/TASK-002-*.md
forbidden_paths:
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - backend/configs/agents.yaml
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-002：结构化 Browser Event

## 目标

将 Go 到浏览器的实时事件收敛为强类型协议，使 Activity、回答正文、Artifact 和
终态互不混用。

## 历史TODO追溯

完整承接“Tool/Progress 事件与最终正文分离”。Citation 事件外壳、元数据、持久化
和 UI 均由 TASK-007 完成，本 Task 不提前实现。

## 当前事实

- Python 已发布 `progress`、`tool.*`、`answer.delta`、`artifact.created` 和 Run 终态；
- Go 当前把 `progress/tool.completed` 投影为普通 `delta`；
- 前端把所有 `delta` 累积到 assistant Markdown；
- Go 最终持久化正文只累积 `answer.delta`，实时与刷新结果可能不同。

## 交付内容

浏览器事件至少区分：

```text
meta
activity
answer_delta
artifact
done
error
```

建立不变量：

```text
assistant_message.content
==
按 sequence 拼接的全部 answer_delta
```

前端只把 `answer_delta` 写入回答正文。Activity 使用独立状态和展示区域；未知事件
安全忽略或进入可观察错误，不得默认为正文。

## 非目标

- 不修改 Python Workflow 或 Prompt；
- 不实现 Create/Attach 分离；
- 不实现 Citation、Proposal 或 Confirmation 协议与 UI；
- 不新增 Skill、Wiki 或 Decision；
- 不新增或改写数据库 Migration；若现有 Schema 无法承载稳定投影，Task 必须退回
  `draft` 重新冻结范围；
- 不展示模型隐藏思维过程。

## 验收标准

- [ ] Browser Event 使用强类型或封闭枚举；
- [ ] `progress/tool.*` 不进入 assistant content；
- [ ] `answer_delta` 是正文唯一增量来源；
- [ ] 实时、刷新和复制正文一致；
- [ ] Activity 只展示服务端白名单字段；
- [ ] 错误和取消保持现有终态语义；
- [ ] Legacy 兼容行为有明确测试；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run test -- --run
cd frontend && npm run lint
cd frontend && npm run build
```

执行前复核前端实际脚本；不存在的命令不得伪造为通过。

## Codex验收与E2E

使用 Browser / Computer Use 验证普通回答和 Research：

- 工具活动不会混入 Markdown；
- 刷新前后正文完全一致；
- 复制内容不含 Activity；
- 失败、取消和空回答不会产生错误正文；
- 历史消息仍可正常展示。

## Handoff

写入 `collaboration/handoffs/TASK-002-round-1.md` 后停止。
