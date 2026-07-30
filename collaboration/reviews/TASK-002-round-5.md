# TASK-002 Review Round 5

## 结论

`changes_requested`

最终实现已经关闭前四轮的协议、白名单、reducer、legacy、测试和 Activity UI 主体
问题；普通回答和 Research 的真实页面验收也证明 Activity 不再进入 Markdown，
复制只包含 answer，刷新后的正文与实时正文一致。

当前仍有一个终态真实性问题：Research 完成或取消后，折叠摘要继续显示
“正在运行”。这与同一条消息的 completed/stopped 终态矛盾，因此 TASK-002 暂不能
标记为 `accepted`。

## Review 输入

- business_round：ROUND-01，状态 `ready`；
- 当前只授权 TASK-002，未启动 TASK-003；
- 审查分支：`grok/TASK-002-browser-event-contract`；
- Handoff：`collaboration/handoffs/TASK-002-round-5.md`；
- 实现提交：`1a53b80`；
- Handoff 提交：`1e2df86`；
- 工作树：审查开始和结束时均干净；
- 远端：当前分支本地领先 2 个提交，未推送。

## 前四轮问题关闭情况

| 问题 | 结果 | 证据 |
|---|---|---|
| Go 白名单纯投影 | 已关闭 | `browser_events.go` 只构造封闭的 Activity/Answer/Artifact 字段 |
| 完整 V1 事件映射 | 已关闭 | route/progress/model/tool/answer/artifact 均有单元测试 |
| legacy thinking 污染正文 | 已关闭 | reducer 把 thinking delta 转为不含原始文本的安全 Activity |
| reducer 未接产品路径 | 已关闭 | `ChatContainer` 对每个事件调用纯 reducer |
| Activity UI 不可达 | 已关闭 | `ChatMessage` 实际渲染 `RuntimeActivityList` |
| unstable id / 数组突变 | 已关闭 | 服务端 sequence id，前端不可变 upsert 和 sequence 排序 |
| frontend unit/lint/diff-check | 已关闭 | 10 个 Vitest 通过，lint 0 error，完整 diff-check 通过 |
| Handoff 不真实或不完整 | 已关闭 | Round-5 Handoff 与真实 diff、命令和风险一致 |

## 验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| Browser Event 强类型/封闭枚举 | 通过 | TypeScript discriminated union、运行时 parser、Go 白名单结构 |
| `progress/tool.*` 不进入正文 | 通过 | Research 页面 Activity 独立折叠区；正文无 Tool 日志 |
| `answer_delta` 是 V1 正文唯一来源 | 通过 | Go builder 和前端 reducer 只追加 answer delta |
| 实时、刷新和复制正文一致 | 通过 | 普通与 Research 均完成复制和刷新复核 |
| Activity 只展示白名单字段 | 通过 | 页面只显示产品化 label/status/duration，无参数、结果或异常 |
| 错误和取消保持终态语义 | 失败 | 取消消息显示“已停止生成”，Activity 摘要同时显示“正在运行” |
| Legacy 兼容行为有测试 | 通过 | legacy thinking/non-thinking reducer 测试；既有 Go legacy 集成场景保留 |
| 不修改禁止范围 | 通过 | 实现增量未进入 Python Workflow、Prompt、Migration 或 Compose |

## Required Skills 复核

- `frontend-design`：Activity 与 answer 已形成独立信息层级，视觉语言与现有聊天卡片
  一致，没有引入无关页面重构。
- `ui-ux-pro-max`：语义按钮、44px 触控高度、稳定 key、运行反馈、终态自动折叠和
  reduced motion 均已实现；但终态摘要仍违反状态反馈真实性。
- `web-design-guidelines`：折叠按钮具有可见 focus、`aria-expanded`、
  `aria-controls`，图标为 decorative，动态摘要使用 `aria-live`，长文本可换行。
  本次阻断不在控件可访问性，而在播报和可见文本的终态内容错误。

## Codex 最小页面验收

运行环境：

- `C:\Users\10245\Desktop\qidianAgent`；
- 本地开发 Compose，`AGENT_PROTOCOL_MODE=v1`；
- frontend/gateway 容器已核对挂载到上述桌面仓库；
- 未修改生产配置。

验收结果：

1. 普通回答：正文正常完成，复制值精确等于可持久化 answer，刷新后不变。
2. Research：运行中显示独立展开的 Activity；观察到 5 次真实工具 started，
   后续 Activity 总数 25；正文不包含 `tavily_search` 或“运行过程”。
3. Research 复制：剪贴板只包含回答正文，不含 Tool/Activity。
4. Research 刷新：正文精确保留；历史 Activity 按 Task 非目标不重建。
5. 取消：空回答没有写入错误正文，消息显示“已停止生成”。
6. 终态缺陷：完成后摘要为“正在运行 · 25 项活动”；取消后摘要为
   “正在运行 · 21 项活动”。

最初打开的开发容器挂载了 `.codex/worktrees/main-runtime` 的旧代码，曾观察到旧
Tool 文本污染；该结果已判定为无效环境证据。重建 frontend/gateway 并确认挂载到
桌面仓库后，正文分离本身通过。

## Codex 独立命令验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd backend && python -m pytest` | 62 passed，2 skipped（未配置 `TEST_DATABASE_URL`） |
| `cd frontend && npm run test -- --run` | 10 passed |
| `cd frontend && npx tsc --noEmit` | 通过 |
| `cd frontend && npm run build` | 通过；保留既有 Browserslist/chunk warning |
| `cd frontend && npm run lint` | 0 error，8 个既有 Fast Refresh warning |
| `git diff --check c544c9e..1e2df86` | 通过 |

首次把 frontend build 与 lint 并行执行时，两者争用 Vite 临时配置文件导致 lint
出现 ENOENT；按仓库已知约束串行重跑后通过，该竞态不计为实现缺陷。

## 问题

### P1

1. `frontend/src/components/chat/RuntimeActivityList.tsx:46`～`:64` 把历史
   `started/running` Activity 当成当前消息仍在运行的依据。当前协议在没有
   invocation id 时按 sequence 保留 started/completed 两条真实事件，因此终态后
   `active` 会永久为 true。真实页面中 completed 消息显示
   “正在运行 · 25 项活动”，stopped 消息同时显示“已停止生成”和
   “正在运行 · 21 项活动”。摘要必须以消息/流的真实终态为准：只有
   `isStreaming` 时才能显示“正在运行”；completed、stopped、failed 应显示不矛盾的
   终态摘要，并同步修正 `aria-live` 文本。

## 必须修改

1. 让 `RuntimeActivityList` 接收足够的消息终态信息，或用等价方式保证终态摘要不再
   由历史 started/running 事件反推。
2. 增加前端测试，覆盖“存在未配对 started Activity，但消息已 completed/stopped/
   failed”时不显示“正在运行”。
3. 复跑 frontend unit、lint、build 和 `git diff --check`。
4. 使用正确挂载的桌面仓库环境复核 Research completed 与 cancel 两个页面终态。
5. 写入 `collaboration/handoffs/TASK-002-round-6.md` 后停止等待复核。

## 下一步

只修复上述 TASK-002 终态摘要问题。不得启动 TASK-003、修改 Task/Round 文件、
切换生产配置、扩大到 Citation 或 Run Supervisor。
