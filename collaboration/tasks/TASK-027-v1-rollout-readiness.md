---
id: TASK-027
title: 完成 V1 发布准备与人工切换门禁
status: draft
executor: grok
base_commit: pending
business_round: RELEASE-GATE
depends_on:
  - TASK-006
  - TASK-024
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#仅剩人工参与"
  - "docs/architecture/agent-runtime-migration-progress.md#P0：V1默认开放前必须完成"
  - "docs/operations/agent-runtime-rollout.md#发布前门禁与分阶段切换"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/scripts/**
  - go-backend/cmd/migrate/**
  - scripts/**
  - docs/operations/**
  - DEPLOYMENT.md
  - README.md
  - docker-compose.dev.yml
  - collaboration/handoffs/TASK-027-*.md
forbidden_paths:
  - docker-compose.yml
  - .env
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - frontend/src/**
  - go-backend/internal/platform/postgres/migrations/**
---

# TASK-027：V1 Rollout Readiness

## 目标

在不修改生产配置、不操作生产数据的前提下，完成 `v1 + postgres + redis` 的发布
准备审计、可重复验证脚本、观测清单和回滚演练材料。

## 交付内容

- 代码、镜像、依赖和 Compose 检查；
- Runtime Schema/Checkpoint setup 的 dry-run 或测试环境验证；
- 最小权限说明；
- `v1 + postgres + redis` 测试环境启动与健康检查；
- P0 和唯一 MVP E2E 报告引用；
- 指标、日志、Trace 和容量观察清单；
- 分阶段切换、停止条件和回滚命令；
- 需要用户/DBA执行的操作清单。

## 安全边界

本Task不授权：

- 修改生产 `docker-compose.yml` 默认值；
- 连接或迁移生产数据库；
- 写入生产 Secret；
- 扩大真实流量；
- 删除 Legacy 回滚路径；
- 自动批准生产发布。

## 验收标准

- [ ] 测试环境 `v1 + postgres + redis` 可重复验证；
- [ ] Schema、权限和 Checkpoint 准备步骤明确；
- [ ] P0 与 MVP E2E 均有可追溯结果；
- [ ] 指标和停止条件可操作；
- [ ] 回滚路径经过非生产演练；
- [ ] 文档不包含 Secret；
- [ ] 所有生产动作明确标为人工；
- [ ] 不修改禁止范围。

## Grok必须验证

执行非生产 readiness、构建、测试和 Compose 配置检查，输出摘要。无法获得的生产
信息必须标记为人工待确认，不能猜测。

## Codex验收与E2E

Codex 检查报告、非生产环境和 Computer Use MVP 链路，确认发布门禁是否齐全。
`accepted` 只代表“具备申请生产切换的条件”，不代表已切换。

## 用户门禁

只有用户明确授权后，才可以按
[`Agent Runtime 上线与回滚`](../../docs/operations/agent-runtime-rollout.md)
执行生产备份、Migration、Secret 配置、小流量切换和扩大流量。

## Handoff

写入 `collaboration/handoffs/TASK-027-round-1.md` 后停止。
