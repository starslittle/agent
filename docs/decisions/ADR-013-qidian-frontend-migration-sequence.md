# ADR-013：ROUND-01 后在 ROUND-02 完成启点前端迁移

> 状态：accepted
>
> 日期：2026-07-31

## 背景

当前前端仍是奇点 AI，对话、流式消息、Activity、取消和深浅色能力已经存在，但品牌
表达和产品信息架构与启点不一致。

启点视觉概念稿同时展示了统一 Skill、个人上下文、Wiki Proposal 和 Decision 等多个
阶段的能力。如果在当前代码上一次实现整张概念稿，会提前伪造 ROUND-03～04 的业务
数据；如果等到所有后端业务完成后再迁移品牌，Wiki 和 Decision 又会继续构建在即将
废弃的奇点 AI 外壳上。

当前 ROUND-01 仍在稳定 Run、恢复、取消和 Citation。此时同时修改品牌、页面外壳和
信息架构，会扩大故障面，使 Runtime 回归与视觉迁移问题难以区分。

## 决策

### 1. ROUND-01 不实施启点正式前端

ROUND-01 继续在当前前端上完成 TASK-004～007 和该轮唯一一次完整产品 E2E。

本轮允许实现 Task 明确要求的 Run 生命周期、Citation 和必要前端修复，但不夹带：

- 奇点 AI 到启点的品牌替换；
- 全局 Design Token 重做；
- 页面外壳和导航重构；
- Skill、Wiki、Proposal 或 Decision 假入口。

ROUND-01 `accepted` 是启点正式前端迁移的前置门禁。

### 2. 前端迁移属于 ROUND-02

不新增独立业务 Round。ROUND-02 按以下顺序实施：

```text
Skill 契约与 Model Catalog
→ Skill Run 协议与 Root Resolver
→ Research / Fortune Skill 接入
→ TASK-012 启点品牌、页面外壳与真实 Skill 交互一次迁移
→ TASK-013 用户 Agent Runs
→ TASK-028 内部只读观测
→ ROUND-02 完整 E2E 与回滚演练
```

TASK-012 等所需 Skill 协议和 available 状态稳定后再执行，避免先写临时菜单、假状态
或第二套前端 Adapter。品牌、视觉基础和 Skill 交互在同一个前端 Task 中完成，减少
对同一组组件反复修改。

### 3. TASK-012 只展示当时真实能力

TASK-012 可以迁移：

- 产品名、助手名、favicon、metadata 和页面文案；
- 全局颜色、字体、圆角、焦点和深浅色 Token；
- 登录页、应用外壳、侧栏、对话空白页和消息视觉；
- `/` Skill 菜单、Skill Chip、选择来源和确认交互；
- ROUND-01 已有的 Activity、Citation、取消、恢复和失败状态；
- 指向 TASK-013 后真实可用 Agent Runs 的导航。

TASK-012 不实现或伪造：

- 个人 Wiki 导航和个人信息数量；
- ContextUsage 和“本次使用的信息”面板；
- Wiki Proposal 和长期记忆写入；
- Decision Skill、决策卡和复盘；
- 概念稿中尚无后端事实源的任何内容。

启点 HTML 概念稿只定义视觉语言和长期气质，不是 TASK-012 的逐像素或全功能验收图。

### 4. ROUND-03～04 只在启点外壳上扩展

ROUND-02 `accepted` 后，启点成为唯一正式前端基线：

- ROUND-03 增加 Wiki、Markdown、Context 和 Proposal；
- ROUND-04 增加 Decision 与复盘体验；
- 不再为新能力适配奇点 AI；
- 回退整个 ROUND-02 时，才回到 ROUND-01 的奇点 AI 稳定前端。

## 原因

- 先固定 Runtime，再改变用户界面，问题定位更清楚；
- Skill UI 等真实协议稳定后一次接入，避免临时字段和重复改造；
- Wiki 和 Decision 不会建立在废弃外壳上；
- 不增加新的业务 Round，也不增加一套并行前端；
- TASK-012 形成清晰的前端迁移提交和局部回退边界；
- 页面不会提前展示不可用能力。

## 后果

正面：

- ROUND-01 验收基线保持稳定；
- ROUND-02 完成后产品身份、统一 Agent 和 Skill 交互一致；
- ROUND-03～04 可以直接复用启点 Design Token 与页面外壳；
- 前端只经历一次主要迁移。

代价：

- ROUND-01 期间仍会看到奇点 AI 品牌；
- TASK-012 的改动范围会同时包含品牌基础和真实 Skill 交互，需要严格控制文件范围；
- ROUND-02 回滚到上一稳定提交时，视觉会同时回到奇点 AI。

## 约束

- 未完成 ROUND-01 验收，不得提前执行 TASK-012；
- 未完成 TASK-011 所需协议与 Skill 接入，不得用前端假数据绕过依赖；
- TASK-012 必须使用 `frontend-design`、`ui-ux-pro-max` 和
  `web-design-guidelines`；
- TASK-012 只迁移当前真实能力，不把 ROUND-03～04 UI 作为占位实现；
- ROUND-02 完整 E2E 必须覆盖启点品牌、普通对话、Research、Fortune、取消、刷新、
  Citation、移动端和深浅色；
- 本 ADR 不授权启动 ROUND-02；ROUND-01 `accepted` 后仍需用户明确授权下一轮。
