---
id: RELEASE-GATE
title: V1 发布准备与人工生产门禁
status: draft
runtime_state: not_deployed
base_commit: pending
accepted_commit: pending
depends_on_rounds:
  - ROUND-04
tasks:
  - TASK-027
codex_round_e2e: required
user_gate: required
---

# RELEASE-GATE：V1 发布准备与人工生产门禁

## 结果

证明已经具备申请生产切换的技术条件：非生产环境可以重复启动和验证，Schema、权限、
Secret、观测、停止条件、能力开关、依赖闭包和回滚步骤均有可操作材料。

本 Gate 不是业务功能轮次，也不代表已经部署或获得生产授权。

## 验收

- TASK-027 `accepted`；
- ROUND-01～04 的验收记录可追溯；
- `v1 + postgres + redis` 非生产验证通过；
- 每个已启用业务层的能力控制和依赖关系清楚；
- 生产备份、Migration、最小权限和 Secret 清单完整；
- 指标、日志、Trace、错误率、延迟和成本停止条件可操作；
- 局部回滚与上一稳定版本切换经过非生产演练；
- 文档不包含 Secret 或真实用户数据。

## 生产边界

即使本 Gate `accepted`，以下动作仍必须由用户另行明确授权：

- 连接、备份或迁移生产数据库；
- 修改生产配置或 Secret；
- 创建 Tag、Push、发布镜像或部署；
- 开启真实流量或扩大流量；
- 执行生产回滚；
- 删除 Legacy 或兼容路径。

## 结论语义

`accepted` 只表示“具备申请生产切换的条件”。实际生产状态记录在独立发布/事故记录
中，不通过修改历史 Round 验收结论表达。
