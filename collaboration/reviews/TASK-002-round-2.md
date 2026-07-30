# TASK-002 Review Round 2

## 结论

`changes_requested`

Round-2 修正了 Browser `answer_delta` 名称，并把 `tool.completed` 从 `delta` 改为
`activity`，但仍未完成 Round-1 Review 的主体要求。legacy thinking delta 依然进入
回答正文，Activity 仍是 `console.log`，强类型协议、白名单投影、Artifact、reducer、
UI 和测试均未实现；本提交也没有 Round-2 Handoff。

## Business Round检查

- business_round：ROUND-01；
- Round状态：`ready`；
- 用户授权：有；
- 审查分支：`grok/TASK-002-browser-event-contract`；
- Round-2 提交：`1849a3d`；
- 本Task是否越过当前Round范围：否；
- Review输入完整性：失败，没有
  `collaboration/handoffs/TASK-002-round-2.md`。

## Round-1问题关闭情况

| Round-1问题 | 结果 | Round-2证据 |
|---|---|---|
| 恢复 legacy `delta` | 部分完成 | 类型已恢复，但 `isThinking=true` 仍追加到正文 |
| Browser 使用 `answer_delta` | 完成 | Go 与 TypeScript 已改为 `answer_delta` |
| Tool/Progress 进入 Activity | 部分完成 | 仅 `progress`、`tool.completed` 改名，载荷仍是松散字符串 |
| Go 白名单纯投影函数 | 未完成 | 仍在 `streamV1` switch 中直接拼任意 JSON |
| Artifact 独立投影 | 未完成 | Go 无 `artifact.created` 分支 |
| 前端纯 reducer 与测试 | 未完成 | 没有新增文件或 test 脚本 |
| RuntimeActivityList | 未完成 | 仍为 TODO + `console.log` |
| Required Skills证据 | 未完成 | 没有 Round-2 Handoff |
| 完整验证与 clean diff | 未完成 | unit/lint/diff check 失败 |

## 验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| Browser Event 强类型/封闭枚举 | 失败 | Activity 只有 `data/isThinking`，缺少 id、sequence、kind、status、label 等冻结字段 |
| `progress/tool.*` 不进入正文 | 失败 | legacy `delta.isThinking=true` 与普通 delta 使用同一正文追加分支 |
| `answer_delta` 是 V1 正文唯一增量 | 部分完成 | V1 名称已正确；legacy 分层仍错误 |
| 实时、刷新和复制正文一致 | 失败 | legacy 实时正文仍会包含 progress/tool thinking 文本 |
| Activity 服务端白名单 | 失败 | Go 直接发送 progress message 和拼接后的 Tool 文本 |
| 错误/取消终态不回归 | 未验证 | 没有新增回归测试或 Handoff 证据 |
| Legacy 兼容测试 | 失败 | 没有测试，实际逻辑违反兼容不变量 |
| Artifact 独立 | 失败 | 只有前端松散声明，没有 Go 投影 |
| 禁止范围 | 通过 | Round-2 只修改 3 个 allowed-path 文件 |

## Required Skills检查

| Skill | 执行者证据 | Reviewer结论 |
|---|---|---|
| `frontend-design` | 无 Round-2 Handoff | 失败；没有 Activity 信息层级与视觉实现 |
| `ui-ux-pro-max` | 无 Round-2 Handoff | 失败；没有动态状态、键盘、焦点或屏幕阅读器实现 |
| `web-design-guidelines` | 无 Round-2 Handoff | 失败；没有可审查控件 |

Reviewer 已重新读取三个 Skill、UI/UX 完整检查表，并拉取最新版 Web Interface
Guidelines。当前 TODO + console 输出不构成用户界面，无法满足语义按钮、可见焦点、
动态内容播报、触摸目标、长文本和响应式要求。

## Codex独立验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test -count=1 ./...` | 通过 |
| `cd backend && python -m pytest` | 通过：62 passed，2 skipped |
| `cd frontend && npm run test -- --run` | 失败：`Missing script: "test"` |
| `cd frontend && npm run lint` | 失败：`ChatContainer.tsx:294` 使用 explicit `any` |
| `cd frontend && npm run build` | 通过，保留既有 bundle/Browserslist warning |
| `cd frontend && npx tsc --noEmit` | 通过 |
| `git diff --check 6053929..1849a3d` | 失败：Round-1 Handoff 尾随空格 |

## Codex独立E2E

- 要求：`required`；
- 环境：本地 Round-2 实现分支；
- Browser / Computer Use：未启动；
- 结果：`failed`；
- 原因：Activity UI 不存在、lint/unit 门禁失败，且 legacy thinking delta 污染正文已
  可由代码确定。此时页面运行不能构成有效验收证据。

## 能力控制与兼容

- 服务端协议开关：未修改；
- V1：answer 增量名称已正确，但 Activity/Artifact 协议不完整；
- legacy：普通 answer 可再次显示，但 thinking/progress/tool delta 仍写入正文；
- Migration与数据：未修改；
- Round回滚：不通过，legacy 组合不能满足正文纯净与刷新一致性。

## 问题

### P0

- 无。

### P1

1. `frontend/src/components/chat/ChatContainer.tsx:293` 对所有 legacy `delta` 追加正文。
   `isThinking=true` 必须转换为 Activity，只有 non-thinking legacy delta 可以进入
   answer；当前实现仍会复制、渲染并实时展示工具/进度日志。
2. `go-backend/internal/httpapi/conversations.go:976` 仍直接透传 progress message，
   且只覆盖 `progress/tool.completed/answer.delta`。缺少
   route/model/tool.started/failed/cancelled、Artifact、安全白名单、malformed/unknown
   处理和 sequence。
3. `frontend/src/lib/chat-api.ts:48` 没有冻结的 `RuntimeActivity` 强类型；
   `artifact.data?: string` 也不是安全引用元数据协议。
4. `frontend/src/components/chat/ChatContainer.tsx:287` Activity 仍只有 TODO 和
   `console.log`；纯 reducer、独立 Activity state、去重、排序、折叠列表、复制隔离和
   无障碍动态状态均未实现。
5. `frontend/src/components/chat/ChatContainer.tsx:294` 新增 explicit `any`，导致
   `npm run lint` 失败；该 cast 本身也没有必要，因为联合类型的两个分支都声明了
   `data`。
6. 提交仍没有 Go 投影/集成测试、legacy 回归测试、前端 reducer 测试、Vitest
   脚本、lockfile 或迁移进度更新。
7. 没有 Round-2 Handoff，无法核对 final commit、修改文件、提交后验证、三个 Skills
   的实际应用、偏差和风险。

### P2

1. `ChatContainer` 仍比较联合类型中不存在且 Go 不会发送的
   `event.type === "tool.completed"`，属于无效兼容分支。
2. Round-1 Handoff 的尾随空格仍导致完整 Task diff 无法通过
   `git diff --check`。

## 必须修改

Round-1 Review 中的完整实现要求继续有效，不能再用事件重命名替代：

1. 完成 Go 白名单纯投影函数和所有冻结事件映射，补齐安全 Artifact 与 sequence；
2. 定义强类型 RuntimeActivity/Artifact，并保留明确 deprecated 的 legacy delta；
3. 实现纯 reducer：legacy thinking delta → Activity，legacy non-thinking delta /
   `answer_delta` → answer；
4. 实现可折叠、语义化、键盘可操作、有可见焦点和动态状态文本的
   RuntimeActivityList；
5. 删除 `any`、console TODO 和不存在的 `tool.completed` Browser 分支；
6. 增加 Go 单元/集成/legacy 测试和前端 reducer Vitest，确保所有验证与
   `git diff --check` 通过；
7. 使用模板提交 `collaboration/handoffs/TASK-002-round-3.md`，记录三个 Required
   Skills 的具体影响和真实提交后验证结果。

## 下一步

Grok 只修复 TASK-002 Round-1/2 Review 中仍未关闭的问题，提交 Round-3 Handoff 后
停止。不得启动 TASK-003、合并 main、修改生产配置或扩大到 Citation/Skill/统一模式。
