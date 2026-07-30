# 文档索引

本目录是项目的长期文档库。涉及 Agent 架构或迁移时，应先阅读产品定位和目标架构。

## 产品

- [产品定位](product/positioning.md)：产品的一句话定位、核心价值和总体演进方向。
- [启点完整产品蓝图](product/future-product.md)：长期产品形态、个人 AI Wiki、Skill Core、决策闭环与多模型入口。
- [启点 Web MVP 产品需求](product/web-mvp.md)：完整 Web 产品阶段、核心页面、Skill、个人 Wiki、决策闭环与演进范围。
- [启点秋招最小 MVP](product/recruiting-mvp.md)：Web MVP 的当前实现子集、唯一验收链路和技术展示目标。

## 架构与迁移

- [Agent Runtime 目标架构](architecture/agent-runtime.md)：当前唯一的目标架构基线、模块边界、迁移阶段和验收标准。
- [Agent Runtime 迁移状态](architecture/agent-runtime-migration-progress.md)：已实现内容、自动验收结果和仅剩人工事项。
- [Agent Runtime P0 稳定化方案](architecture/agent-runtime-p0-stabilization-plan.md)：合入 main 前的 Run 控制协议、事件分层和自动验收计划。
- [统一助手与 Skill 目标架构](architecture/unified-agent-skill-architecture.md)：一个助手、多种 Skill、个人上下文与 Human-in-the-loop 的目标边界。
- [统一助手、Skill 与个人 Wiki 迁移实施方案](architecture/unified-agent-skill-migration-plan.md)：当前代码起点、历史 TODO 追溯、普通/Research 链路结合点、实施顺序与验收门禁。
- [Agent Core 未来扩展候选](architecture/agent-core-future-options.md)：尚未决策的 ExecutionPlan、多 Skill、通用行动循环、持久 HITL、上下文规划与 Eval 方向；不属于当前 Task 授权。
- [Go/Python 迁移背景](architecture/go-python-migration-history.md)：历史决策、协议设计和迁移记录；与目标架构冲突时以前者为准。

## 运维

- [Agent Runtime 上线与回滚](operations/agent-runtime-rollout.md)：生产备份、schema、权限、分阶段切换、观测、回滚与人工批准清单。

## 决策与协作

- [架构决策记录](decisions/README.md)：已经接受或正在评审的跨模块架构决定。
- [Codex / Grok 协作区](../collaboration/README.md)：Task、Handoff、Review 与职责分工。
- [业务交付轮次](../collaboration/rounds/README.md)：五个可独立验收的业务增量、能力控制和局部回滚边界。
