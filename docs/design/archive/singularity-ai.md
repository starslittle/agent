# 奇点 AI 设计档案

> 状态：archived
>
> 归档日期：2026-07-31
>
> 源码基线：`design/singularity-ai-archive` → `8d00829`

## 1. 档案定位

奇点 AI 是启点产品演进前的 Web 对话界面。

它只作为历史设计参考保留：

- 不作为后续产品模式；
- 不提供运行时切换；
- 不继续接入新的 Agent、Skill、Wiki 或 Decision 能力；
- 不承担后续兼容、响应式、可访问性和 E2E 要求。

启点是唯一正式演进方向。

## 2. 视觉特征

奇点 AI 的主要视觉语言包括：

- 紫色到蓝色的 AI 渐变；
- “奇”字品牌图形；
- 宇宙轨道与旋转圆环；
- 深色科技背景与发光效果；
- 玻璃拟态卡片；
- “深度思考”模式开关；
- 以聊天与模型能力为中心的产品表达。

这些元素共同形成了完成度较高的通用 AI 对话工具外观，但不能准确表达启点的个人
Wiki、长期上下文和决策闭环，因此不继续作为新产品设计基线。

## 3. 如何查看

归档源码不在当前目录复制。需要查看时使用 Git Tag：

```bash
git show design/singularity-ai-archive:frontend/src/pages/Index.tsx
git worktree add <temporary-path> design/singularity-ai-archive
```

临时 worktree 只用于历史查看或采集截图，使用后可以安全移除；不要在该 Tag 上继续
开发。

关键文件：

| 文件 | 内容 |
| --- | --- |
| `frontend/src/pages/AuthPage.tsx` | 登录与注册页 |
| `frontend/src/pages/Index.tsx` | 应用外壳与对话页头部 |
| `frontend/src/components/chat/ChatSidebar.tsx` | 品牌、历史对话与侧栏 |
| `frontend/src/components/chat/ChatContainer.tsx` | 对话空白页和消息区域 |
| `frontend/src/components/chat/ChatInput.tsx` | 输入框与深度思考入口 |
| `frontend/src/components/chat/ChatMessage.tsx` | 助手消息与 Activity |
| `frontend/src/index.css` | 紫蓝品牌 Token 与深浅色主题 |
| `frontend/public/favicon.svg` | “奇”字 favicon |

## 4. 与启点的关系

奇点 AI 记录的是“通用 AI 对话工具”阶段，启点则转向：

```text
个人信息
→ 相关上下文
→ Skill 分析
→ 用户确认
→ Wiki / Decision / Review 沉淀
```

启点可以复用原前端中成熟的会话、流式消息、Activity、取消和深浅色实现，但不需要
保留奇点 AI 的品牌外观或模式入口。

新方向见：

- [`启点 Web 视觉与交互设计基线`](../qidian-web-visual-ux-spec.md)
- [`启点工作区 HTML 概念稿`](../previews/qidian-workspace-concept.html)
- [`ADR-012：奇点 AI 只作为设计档案保留`](../../decisions/ADR-012-singularity-ui-design-archive.md)
