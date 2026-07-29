# 文档索引

本目录是项目的长期文档库。涉及 Agent 架构或迁移时，应先阅读产品定位和目标架构。

## 产品

- [产品定位](product/positioning.md)：产品目标、MVP 与长期闭环。

## 架构与迁移

- [Agent Runtime 目标架构](architecture/agent-runtime.md)：当前唯一的目标架构基线、模块边界、迁移阶段和验收标准。
- [Agent Runtime 迁移状态](architecture/agent-runtime-migration-progress.md)：已实现内容、自动验收结果和仅剩人工事项。
- [Agent Runtime P0 稳定化方案](architecture/agent-runtime-p0-stabilization-plan.md)：合入 main 前的 Run 控制协议、事件分层和自动验收计划。
- [Go/Python 迁移背景](architecture/go-python-migration-history.md)：历史决策、协议设计和迁移记录；与目标架构冲突时以前者为准。

## 运维

- [Agent Runtime 上线与回滚](operations/agent-runtime-rollout.md)：生产备份、schema、权限、分阶段切换、观测、回滚与人工批准清单。
