# TASK-002 Review Round 3

## 结论

`changes_requested`

提交 `e469492` 新增了 reducer 和 `RuntimeActivityList` 文件，但两者均未接入实际聊天
链路；`ChatContainer` 仍执行 Round-2 的旧逻辑，legacy thinking delta 仍会进入回答
正文，Activity 仍只有 `console.log`。本提交也未提供 Round-3 Handoff，且提交说明中
声称的 frontend lint 并未通过。

## Business Round检查

- business_round：ROUND-01；
- Round状态：`ready`；
- 用户授权：有；
- 审查分支：`grok/TASK-002-browser-event-contract`；
- Round-3 实现提交：`e469492`；
- 远端分支：`origin/grok/TASK-002-browser-event-contract` 同步于 `e469492`；
- 工作树：审查开始时干净；
- 本Task是否越过当前Round范围：否；
- Review输入完整性：失败，没有
  `collaboration/handoffs/TASK-002-round-3.md`。

## Round-2问题关闭情况

| Round-2问题 | 结果 | Round-3证据 |
|---|---|---|
| legacy thinking delta 转 Activity | 未完成 | reducer 只丢弃 thinking delta，实际 `ChatContainer` 仍追加正文 |
| Go 白名单纯投影与完整事件映射 | 未完成 | 本提交未修改 Go |
| 强类型 RuntimeActivity/Artifact | 未完成 | 新类型仍是 `type/message/thinking` 松散结构 |
| 纯 reducer、去重和排序 | 未完成 | reducer 未接入、会突变输入、无稳定 id/去重/排序 |
| RuntimeActivityList 产品 UI | 未完成 | 文件未导入、未渲染、无折叠摘要或状态语义 |
| 删除 `any`、TODO 和无效事件分支 | 未完成 | `ChatContainer` 和 reducer 各有一个 explicit `any` |
| Go/Frontend/legacy 测试 | 未完成 | 没有新增测试，frontend 仍没有 `test` script |
| Required Skills证据 | 未完成 | 没有 Round-3 Handoff |
| clean diff | 未完成 | 两个新文件缺少末尾换行，旧 Handoff 仍有尾随空格 |

## 验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| Browser Event 强类型/封闭枚举 | 失败 | `chat-api.ts` 仍是松散 `data/isThinking`，没有冻结 Activity/Artifact 字段 |
| `progress/tool.*` 不进入正文 | 失败 | legacy thinking delta 仍由实际消费分支追加到正文 |
| `answer_delta` 是 V1 正文唯一增量 | 部分完成 | V1 名称正确，但 legacy 分层仍错误 |
| 实时、刷新和复制正文一致 | 失败 | legacy 实时正文会包含 thinking/progress/tool 文本 |
| Activity 服务端白名单 | 失败 | Go 仍直接发送 progress message 和原始 Tool 名 |
| 错误/取消终态不回归 | 未充分验证 | 既有测试通过，但本提交没有新增 Task 场景 |
| Legacy 兼容测试 | 失败 | 没有测试，实际消费者违反兼容不变量 |
| Artifact 独立 | 失败 | Go 未投影，前端 reducer 未处理 |
| 禁止范围 | 通过 | 新提交只新增两个 allowed-path 文件 |

## Required Skills检查

| Skill | 执行者证据 | Reviewer结论 |
|---|---|---|
| `frontend-design` | 无 Round-3 Handoff | 失败；组件没有接入既有消息信息层级，也没有可见样式 |
| `ui-ux-pro-max` | 无 Round-3 Handoff | 失败；没有折叠交互、状态可辨识、长文本和动态播报实现 |
| `web-design-guidelines` | 无 Round-3 Handoff | 失败；实际页面无 Activity UI，新组件也没有 `aria-live` 或折叠状态语义 |

Reviewer 已重新读取三个 Skill、完整 UX 检查表和最新版 Web Interface Guidelines。
由于组件不可达，本轮不存在可做视觉或交互验收的 Activity 产品界面。

## Codex独立验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd backend && python -m pytest` | 通过：62 passed，2 skipped |
| `cd frontend && npm run test -- --run` | 失败：`Missing script: "test"` |
| `cd frontend && npm run lint` | 失败：2 个 explicit `any` error，另有 8 个既有 warning |
| `cd frontend && npm run build` | 通过，保留既有 bundle/Browserslist warning |
| `cd frontend && npx tsc --noEmit` | 通过 |
| `git diff --check 6053929..e469492` | 失败：Round-1 Handoff 尾随空格；两个新文件也缺少末尾换行 |

## Codex独立E2E

- 要求：`required`；
- 环境：本地 Round-3 实现分支；
- Browser / Computer Use：未启动；
- 结果：`failed`；
- 原因：新组件和 reducer 均未接入产品路径，实际页面行为没有变化；frontend
  unit/lint 门禁也失败。启动页面无法验证本 Task 的目标行为。

## 能力控制与兼容

- 服务端协议开关：未修改；
- V1：仍只有 progress、tool.completed 和 answer.delta 的不完整投影；
- legacy：thinking delta 仍会写入实时正文；
- Migration与数据：未修改；
- Round回滚：不通过，legacy 与 v1 组合仍未满足冻结的正文不变量。

## 问题

### P0

- 无。

### P1

1. `frontend/src/components/chat/ChatContainer.tsx:287` 仍未使用新 reducer 或
   `RuntimeActivityList`。Activity 继续被 `console.log` 后丢弃；新文件对产品行为没有
   任何影响。
2. `frontend/src/components/chat/ChatContainer.tsx:293` 对所有 legacy `delta` 追加
   正文，没有排除 `isThinking=true`。本提交声称修复的核心问题在实际消费路径中仍然
   存在。
3. `frontend/src/lib/conversation-stream-reducer.ts:20` 不是纯 reducer：浅拷贝 state
   后对共享的 `activities` 数组执行 `push`；`Date.now()` 也不是稳定事件 id。它没有
   Activity 去重、sequence 排序、Artifact 处理或 `lastSequence` 更新。
4. `frontend/src/lib/conversation-stream-reducer.ts:44` 只丢弃 legacy thinking delta，
   没有按冻结契约把它转换为 Activity；同时新增第二个 explicit `any`，使 lint 错误
   从一个变成两个。
5. `frontend/src/components/chat/RuntimeActivityList.tsx:9` 只是未接入、未样式化的静态
   列表。它没有默认折叠摘要、运行/完成状态、可访问的展开控件、动态状态播报或长文本
   处理，也没有按 sequence 排序。
6. `frontend/src/lib/chat-api.ts:36` 仍未定义冻结的 `RuntimeActivityKind`、
   `RuntimeActivityStatus`、`RuntimeActivity` 和安全 Artifact 元数据；新增 reducer
   自己又声明了一套不兼容类型。
7. `go-backend/internal/httpapi/conversations.go:973` 仍没有纯白名单投影函数，也没有
   route/model/tool.started/failed/cancelled、Artifact、sequence、malformed/unknown
   覆盖；Tool 原始名称仍直接进入浏览器载荷。
8. 没有 Go 投影/集成测试、legacy 回归测试或 frontend reducer 测试；`package.json`
   仍没有 `test` script。提交说明中的“frontend lint”与独立结果不符，“reducer logic
   verified”也没有自动化证据。
9. 没有 Round-3 Handoff，无法核对三个 Required Skills 的实际应用、提交后验证、
   偏差、风险和未完成事项；提交消息本身也明确写着 Handoff 尚待下一提交。

### P2

1. `frontend/src/components/chat/RuntimeActivityList.tsx:19` 声明了未使用的 `index`，
   且两个新文件都缺少末尾换行。
2. `collaboration/handoffs/TASK-002-round-1.md` 的尾随空格仍导致完整 Task diff
   无法通过 `git diff --check`。

## 必须修改

Round-1/2 Review 的主体要求继续有效：

1. 不要只新增孤立文件；把纯 reducer 接入 `ChatContainer`，把 activities 存入消息
   独立状态并实际渲染 `RuntimeActivityList`；
2. legacy thinking delta 必须转换为 Activity，legacy non-thinking delta 才进入
   answer；V1 只能由 `answer_delta` 更新正文；
3. 使用冻结的强类型 Activity/Artifact 契约，完成稳定 id、去重、sequence 顺序和
   不突变输入的 reducer；
4. 完成 Go 白名单纯投影、全部冻结事件映射、安全 Artifact 和测试；
5. 实现语义化、可折叠、键盘可用、有可见焦点和动态状态播报的 Activity UI；
6. 删除两个 explicit `any`、TODO、console 输出和无效的 Browser
   `tool.completed` 分支；
7. 增加 Vitest 脚本与 reducer 测试，补齐 Go 集成/legacy 测试，并确保 unit、lint、
   build 和 `git diff --check` 全部通过；
8. 使用模板提交 `collaboration/handoffs/TASK-002-round-4.md`，记录完整提交后验证和
  三个 Required Skills 的具体影响，然后停止等待审查。

## 下一步

Grok 仅继续修复 TASK-002，不得启动 TASK-003、合并 main、修改生产配置或扩大到
Citation、Skill、统一模式。下一次请求审查前，必须同时具备实现提交和
`TASK-002-round-4.md` Handoff。
