---
id: TASK-028
title: 扩展 Agent Runs 内部只读观测模式
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-013
source_todos:
  - "docs/product/recruiting-mvp.md#7.3：Agent Runs与内部只读观测"
  - "docs/architecture/unified-agent-skill-architecture.md#10.1：Agent Runs与内部观测"
  - "docs/architecture/unified-agent-skill-migration-plan.md#M8：统一助手前端与Agent Runs"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/auth/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/**
  - go-backend/internal/platform/postgres/store.go
  - go-backend/internal/platform/postgres/conversation_store.go
  - go-backend/internal/platform/postgres/**/*_test.go
  - go-backend/internal/platform/postgres/migrations/*_agent_observability_access.sql
  - frontend/src/features/runs/**
  - frontend/src/pages/**
  - frontend/src/auth/**
  - frontend/src/lib/auth-api.ts
  - frontend/src/lib/run-api.ts
  - frontend/src/App.tsx
  - frontend/src/App.css
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-028-*.md
forbidden_paths:
  - backend/**
  - go-backend/internal/platform/postgres/migrations/001_auth_foundation.sql
  - go-backend/internal/platform/postgres/migrations/002_conversation_foundation.sql
  - go-backend/internal/platform/postgres/migrations/003_agent_protocol_v1.sql
  - go-backend/internal/platform/postgres/migrations/004_agent_observability.sql
  - go-backend/internal/platform/postgres/migrations/005_agent_runtime_foundation.sql
  - docker-compose.yml
---

# TASK-028：Agent Runs 内部只读观测模式

## 目标

在 TASK-013 的用户侧 Agent Runs 基础上增加最小内部观测模式。两种模式共用 Go
侧脱敏 Run 投影、查询模型和前端展示组件，但使用独立服务端权限与路由，避免把
跨用户能力扩散到普通用户 API。

## 当前事实

- 当前 `GET /api/v1/agent-runs` 和详情 API 始终使用 Session User ID 查询；
- PostgreSQL Store 已验证跨用户 Run Detail 返回 not found；
- 当前用户和 Session 模型没有管理员角色；
- Go 已持久化 Run、Span、Event、Prompt Hash、Usage、耗时和错误等观测投影；
- 浏览器不应直接访问 Python Runtime Store、Redis 或原始服务日志。

## 输入与输出契约

- 增加最小权限 `observability_admin`，现有用户默认保持普通 `user`；
- 不提供通过产品 API 自助提升权限的入口，内部权限只能由受控运维流程配置；
- 普通用户 Run API 的用户所有权语义保持不变；
- 管理员使用独立只读 API 查询脱敏 Run 列表和详情；
- 列表至少支持用户 ID、Skill、Workflow、Model、状态、错误码和时间范围筛选；
- 管理员详情复用 TASK-013 的时间线、Span、Usage、Citation、Artifact 和
  provenance 展示；
- 管理员的跨用户列表和详情读取进入审计记录，不记录完整返回内容。

具体路径和分页格式在 Task 进入 `ready` 前根据当时路由复核冻结，不允许执行者自行
把普通用户 API 改成可跨用户查询。

## 实现约束

- Go/PostgreSQL 仍是 Product Run 和观测权限的事实源；
- 服务端先鉴权、再查询、再脱敏，不能依赖前端隐藏字段；
- 页面只能消费 Go 的稳定投影，不能查询 Python Runtime 或 Redis；
- 同一字段在用户模式和内部模式使用同一格式化与状态映射组件；
- 管理员只读，不提供取消、重放、重试、编辑 Wiki、修改 Decision 或生产控制；
- 不显示完整 Prompt、模型隐藏思维链、Secret、Cookie、连接串、完整用户消息或
  未脱敏工具输入输出；
- 不建设独立日志、指标、Trace 或告警平台。

## 非目标

- 通用 RBAC/组织权限系统；
- 管理员账号和权限管理页面；
- 原始日志搜索和 Stack Trace 浏览；
- 告警、值班、成本结算或运营报表；
- Run 重放、人工改状态或其他写操作；
- 单独部署观测服务或复制一份 Run 数据。

## 验收标准

- [ ] 普通用户仍只能查询自己的 Run，不能看到内部入口；
- [ ] 普通用户直接请求管理员 API 得到稳定拒绝；
- [ ] `observability_admin` 可以按规定条件筛选脱敏 Run；
- [ ] 管理员可以打开跨用户 Run 详情，但看不到完整会话正文和敏感字段；
- [ ] 用户模式和内部模式复用时间线、状态、Usage 和 provenance 组件；
- [ ] 管理员界面没有取消、重放、修改数据或生产控制按钮；
- [ ] 跨用户列表和详情访问留下不含返回正文的审计记录；
- [ ] 空状态、无权限、加载、分页和查询失败均有明确表达；
- [ ] 既有 Run 所有权、取消和详情接口测试不回归。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

增加 Go 集成测试覆盖普通用户拒绝、管理员筛选、跨用户详情、脱敏和审计；增加前端
组件或页面测试覆盖权限入口、筛选、空状态和只读约束。

Task 进入 `ready` 时必须按当时 Migration 目录分配下一个序号，并把
`*_agent_observability_access.sql` 收窄为唯一文件名。不得假设它仍是 `006`，也不得
改写已有 Migration。

## Codex验收与E2E

使用 Browser / Computer Use 分别以普通用户和 `observability_admin` 登录：

1. 普通用户只能看到自己的 Run，直接访问内部地址或 API 均被拒绝；
2. 管理员按用户、Skill、状态和错误筛选，并打开其他用户的完成、取消和失败 Run；
3. 核对两种模式的共同字段与状态表达一致；
4. 检查页面没有写操作，也没有完整 Prompt、用户正文、Secret 或原始工具载荷；
5. 检查跨用户访问产生脱敏审计记录。

## Handoff

写入 `collaboration/handoffs/TASK-028-round-1.md` 后停止。
