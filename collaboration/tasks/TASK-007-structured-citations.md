---
id: TASK-007
title: 建立结构化 Citation 投影持久化与渲染
status: draft
executor: grok
base_commit: pending
business_round: ROUND-01
depends_on:
  - TASK-006
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#其他产品与平台TODO：结构化Citation展示"
  - "docs/architecture/unified-agent-skill-architecture.md#10：浏览器事件"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/artifacts.py
  - backend/agent/workflows/research_v1/**
  - backend/tests/**
  - go-backend/internal/agent/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/platform/postgres/**
  - frontend/src/lib/**
  - frontend/src/components/chat/**
  - frontend/src/features/citations/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-007-*.md
forbidden_paths:
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/workflows/chat_v1/**
  - backend/configs/agents.yaml
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-007：结构化 Citation

## 目标

将 Research 已产生的 Citation/Evidence 从内部 ID 转换为可持久、可回放、可点击的
结构化产品数据。

## 数据契约

至少包含：

```text
citation_id
title
url
snippet
source_type
artifact_id
sequence
```

Citation 作为结构化事件和消息/Run 关联数据存在，不伪装成回答正文。

## 实现约束

- `citation_id` 稳定关联来源；
- Go 持久化经过脱敏和长度限制的数据；
- 实时、刷新、复制和 Re-attach 语义一致；
- 前端将引用渲染为可点击角标与来源列表；
- 不使用正则把任意 `[text]` 猜成引用；
- 没有来源元数据时保留普通文本，不生成伪链接。

## 非目标

- 不优化 Research 检索策略；
- 不改变搜索 Provider；
- 不增加通用网页抓取；
- 不重写 Research Workflow。
- 不新增或改写数据库 Migration；如果现有 Citation/Event 投影无法满足持久化契约，
  Task 必须退回 `draft` 并显式增加 Migration 范围。

## 验收标准

- [ ] Citation 可通过 Run/Event/Message 恢复；
- [ ] 正文角标和来源列表稳定对应；
- [ ] 刷新后引用仍可点击；
- [ ] 复制行为有明确产品规则并一致；
- [ ] 无效 URL 和缺失元数据安全降级；
- [ ] Citation 不进入 Activity 或正文以外的错误通道；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

执行前按实际影响范围收窄或补充命令。

## Codex验收与E2E

使用 Browser / Computer Use 发起 Research，验证实时角标、来源列表、链接、安全
属性、刷新恢复、重新附着和复制结果。

## Handoff

写入 `collaboration/handoffs/TASK-007-round-1.md` 后停止。
