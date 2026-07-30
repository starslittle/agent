---
id: TASK-016
title: 建立 Context Package 组装使用与审计
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-011
  - TASK-014
source_todos:
  - "docs/product/recruiting-mvp.md#12：标准运行流程"
  - "docs/architecture/unified-agent-skill-architecture.md#8：上下文组装"
  - "docs/architecture/unified-agent-skill-architecture.md#12：状态所有权"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/context/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/agent/**
  - go-backend/internal/agentclient/**
  - go-backend/internal/platform/postgres/context_*.go
  - go-backend/internal/platform/postgres/*context*_test.go
  - go-backend/internal/platform/postgres/conversation_store.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_context_package.sql
  - backend/app/api/agent_runs.py
  - backend/app/runtime/**
  - backend/agent/context.py
  - backend/agent/application.py
  - backend/agent/graph.py
  - backend/agent/root/**
  - backend/agent/state.py
  - backend/tests/**
  - frontend/src/components/chat/**
  - frontend/src/features/wiki/**
  - frontend/src/lib/**
  - collaboration/handoffs/TASK-016-*.md
forbidden_paths:
  - backend/agent/workflows/research_v1/**
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/tools/**
  - backend/agent/prompts/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-016：Context Package

## 目标

由 Go 根据当前用户、请求用途、Skill、状态和授权组装最小 Context Package，Python
只消费包内容；Run 记录实际使用的 Item/Revision 和用途。

## Resolve → Context → Execute 协议

自动路由由 Python Root Skill Resolver 完成，而个人事实由 Go 拥有。为避免“Go
不知道 Skill 就无法按用途取 Context”和“Python 为路由读取整个 Wiki”的循环依赖，
本 Task 必须建立同一 Product Run 内的两阶段内部协议：

```text
1. Go 创建 Product Run 和稳定 execution identity
2. Go 使用当前请求、会话历史和最小非 Wiki 路由元数据调用 Python Resolver
3. Python 返回并记录 SkillResolution / ContextRequirements
4. Go 校验结果并组装、冻结 ContextPackage
5. Go 使用同一 Product Run 启动 Python execution
6. Python 校验并复用冻结的 resolution，不再次自动路由
```

显式 Skill 仍须经过存在性、available、权限、风险和模型能力校验，但可以跳过路由
模型。Direct Answer 可以返回 `primary_skill=null`，并按明确的
`ContextRequirements` 决定是否读取少量个人上下文。

实现只能复用 TASK-010 的同一个 Skill Resolver 组件。可以增加签名保护的内部
resolve API，例如 `POST /internal/v1/agent-routes:resolve`，但不能复制第二套路由
Prompt、Registry 或决策逻辑。

路由结果、路由模型 Usage、Context Package 和最终 execution 都归属于同一 Product
Run。重试和 Re-attach 必须复用已经冻结的 resolution/package；冲突值失败关闭，
不能因重连改变历史依据。

## Context契约

至少包含：

```text
package_id
purpose
items[].item_id
items[].revision_id
items[].type
items[].domain
items[].content
items[].source
items[].updated_at
policy.allow_memory_proposals
```

`ContextRequirements` 至少表达：

```text
execution_mode
primary_skill
purpose
needs_personal_context
allowed_types/domains
item/character budget
```

跨服务事件默认只携带 ID、类型和安全摘要，不重复传播全部敏感正文。

## 组装策略

第一版使用确定性过滤：

- 当前 user；
- confirmed/允许的状态；
- domain/type；
- 时间和是否过期；
- Skill 声明的上下文需求；
- 明确的数量与字符预算；
- 简单全文匹配或规则排序。

不因数据量很小提前引入复杂向量系统。

## 非目标

- 不允许 Python 直查 Wiki 表；
- 不实现向量数据库；
- 不自动写 Wiki；
- 不实现 Decision 专属排序；
- 不把整个 Wiki 默认发送给模型。
- 不实现多 Skill、Skill 依赖 DAG、Research 支持能力或通用 ExecutionPlan；
- 不让 Python 通过内部 API 回查 Wiki 正文。

## 验收标准

- [ ] 用户隔离和状态过滤正确；
- [ ] 自动路由在读取 Skill 专属 Wiki Context 前完成，且路由阶段不接收整个 Wiki；
- [ ] 显式、自动和 Direct 三条路径使用同一个 Resolver 契约；
- [ ] execution 不重复路由，重试/重连不改变 resolution 或 Context Package；
- [ ] outdated/rejected/forgotten 默认不进入；
- [ ] Context 预算生效；
- [ ] Run 冻结实际 Item/Revision；
- [ ] 页面可查看本次使用的上下文；
- [ ] 修改 Wiki 不改变历史 Run 依据；
- [ ] 无上下文时安全退化；
- [ ] 日志和事件不泄露完整敏感正文。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

Task 进入 `ready` 时必须冻结 resolve API、签名输入、超时和失败回退，并按当时
Migration 目录分配下一个序号，把 `*_context_package.sql` 收窄为唯一文件名；禁止
改写已有 Migration。

## Codex验收与E2E

使用 Browser / Computer Use 创建多种状态 Wiki Item，发起对话，检查实际引用、页面
说明、Run ContextUsage、历史版本和被遗忘信息不会继续使用。

## Handoff

写入 `collaboration/handoffs/TASK-016-round-1.md` 后停止。
