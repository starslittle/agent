# TASK-002 Review Round 1

## 结论

`changes_requested`

当前提交只完成了少量事件名称替换，尚未形成 TASK-002 要求的 Go → Browser →
Frontend 完整协议闭环。生产默认仍可能使用的 legacy `delta` 已失去前端消费路径，
Activity UI、纯 reducer、安全白名单、Artifact 投影和协议测试均未实现，不能进入
产品级 E2E 或合并。

## Business Round检查

- business_round：ROUND-01；
- Round状态：`ready`；
- 用户授权：有，授权记录位于 ROUND-01；
- 本Task是否越过当前Round范围：否；
- 实现分支：`grok/TASK-002-browser-event-contract`；
- 审查提交：`23cd8e0`；
- 基准：Task 记录 `634d908`，实现分支实际基于授权提交 `6053929`；两者之间只有
  TASK/ROUND 授权文档，不构成代码冲突。

## 验收矩阵

| 验收项 | 结果 | 证据 |
|---|---|---|
| Browser Event 使用强类型或封闭枚举 | 失败 | `activity` 仍使用松散字符串字段；冻结名称 `answer_delta` 被实现为 `answer.delta` |
| `progress/tool.*` 不进入 assistant content | 失败 | Go 仍把 `tool.completed` 投影为 `delta("已完成工具：...")` |
| `answer_delta` 是正文唯一增量来源 | 失败 | Browser 事件名错误；legacy `delta` 消费被删除 |
| 实时、刷新和复制正文一致 | 未验证 | legacy 实时正文会为空；缺少 reducer 与产品 E2E 前提 |
| Activity 只展示服务端白名单字段 | 失败 | Go 直接传递 progress `message`，前端只执行 `console.log` |
| 错误和取消保持现有终态语义 | 未验证 | 没有新增协议/回归测试；legacy 主路径已断 |
| Legacy 兼容行为有明确测试 | 失败 | 联合类型删除 `delta`，且提交没有任何测试文件 |
| Artifact 独立且不进入正文 | 失败 | 前端仅声明松散 `artifact.data`，Go 没有 Artifact 投影 |
| 不修改禁止范围 | 通过 | 变更文件均未进入 forbidden paths |
| `git diff --check` | 失败 | Handoff 第 3～7 行存在尾随空格且文件缺少结尾换行 |

## Required Skills检查

| Skill | 执行者证据 | Reviewer结论 |
|---|---|---|
| `frontend-design` | Handoff 未记录 | 失败；没有独立 Activity 信息层级或 UI |
| `ui-ux-pro-max` | Handoff 未记录 | 失败；没有可折叠交互、状态反馈或无障碍实现 |
| `web-design-guidelines` | Handoff 未记录 | 失败；没有可供验收的 Activity 控件 |

Reviewer 已完整读取三个 Skill，并按最新版 Web Interface Guidelines 复核。当前只存在
`console.log`，因此键盘操作、焦点、触摸目标、状态文本、响应式和可访问性均无法通过。

## Codex独立E2E

- 要求：`required`；
- 环境：本地实现分支，静态审查与独立命令验证；
- 用户旅程：普通回答、Research Activity、刷新、复制、失败和取消；
- Browser / Computer Use观察：未启动；
- 结果：`failed`；
- 证据：legacy 回答消费已被代码层确定性破坏，Activity UI 未实现，继续运行页面
  E2E 只会重复已知失败，不构成有效验收。

## Codex独立验证

| 命令或检查 | 结果 |
|---|---|
| `cd go-backend && go test ./...` | 通过，但提交没有新增投影或集成测试，结果主要来自既有测试 |
| `cd frontend && npm run test -- --run` | 失败：`Missing script: "test"` |
| `cd frontend && npm run lint` | 通过，8 个既有 Fast Refresh warning |
| `cd frontend && npm run build` | 通过，有既有 bundle size 与 Browserslist warning |
| `cd frontend && npx tsc --noEmit` | 通过 |
| `git diff --check 6053929..23cd8e0` | 失败：Handoff 尾随空格 |

第一次并行运行 lint/build 时，Vite 临时配置文件与 ESLint 扫描发生竞态；build 完成后
串行重跑 lint 通过，因此该次 ENOENT 不计为实现缺陷。

## 能力控制与兼容

- 服务端关闭行为：本 Task 未修改生产协议开关；
- 前端行为：不兼容 legacy；收到旧 `delta` 时全部忽略，最终会进入“未收到任何内容”
  失败路径；
- Migration与旧代码兼容：未新增 Migration；旧 Browser Event 兼容失败；
- 数据保留：未修改；
- 对Round回滚边界的结论：不通过。切回 legacy 后当前前端无法消费回答，不能作为
  ROUND-01 的回滚组合。

## 问题

### P0

- 无。

### P1

1. `frontend/src/lib/chat-api.ts:48` 删除了 deprecated legacy `delta` 分支。当前生产
   默认仍可能走 legacy，`ChatContainer` 会忽略所有回答增量并把正常请求判为失败。
2. `go-backend/internal/httpapi/conversations.go:991` 仍将 `tool.completed` 投影为正文
   形态的 `delta`；`progress/tool/model/route` 没有统一映射为强类型 Activity，
   未知事件和敏感字段也没有通过纯白名单投影函数处理。
3. `go-backend/internal/httpapi/conversations.go:1007` 使用 `answer.delta` 作为 Browser
   事件名，违反已冻结的 `answer_delta` 协议；Artifact 也没有实际投影。
4. `frontend/src/components/chat/ChatContainer.tsx:287` 只把 Activity 输出到控制台，
   没有独立 state、纯 reducer、去重、稳定 sequence、`RuntimeActivityList` 或可折叠
   UI，因此信息架构、复制隔离和可访问性均未交付。
5. 没有新增 Go 投影单元/集成测试、legacy 回归测试、前端 reducer 测试或 Vitest
   脚本。Handoff 记录的是“pre-change/baseline”验证，不能证明提交后的行为。
6. Handoff 明确列出协议和 UI 未完成，却使用 `completed`，并遗漏模板要求的
   `ready_for_review` 状态、final commit、branch/worktree、修改文件、行为变化、
   三个 Required Skills、偏差和风险。

### P2

1. Handoff 存在尾随空格、缺少结尾换行，`git diff --check` 失败。
2. 实现分支已推送到 `origin`，但授权指令要求未经审查不要推送；后续修复不得继续
   扩大外部状态变更。

## 必须修改

1. 按迁移方案提取无 I/O 的 Go Browser Event 纯投影函数：
   - `progress/tool.*/model.*/route.*` → 白名单 `activity`；
   - `answer.delta` → Browser `answer_delta`；
   - `artifact.created` → 仅安全引用元数据；
   - 未知或 malformed 事件不得进入正文且不得 panic。
2. TypeScript 联合类型保留 deprecated legacy `delta`，并定义强类型
   `RuntimeActivity`、`answer_delta`、`artifact`；不得使用原始字符串载荷代替产品
   投影。
3. 新增纯 `conversation-stream-reducer`：
   - 只有 `answer_delta` 和 legacy non-thinking `delta` 追加正文；
   - Activity、legacy thinking delta、Artifact、done/error 不进入正文；
   - 按稳定 ID 去重，并按 sequence 保留多次真实工具调用。
4. 新增独立、语义化、可键盘操作且有清晰状态文本的可折叠
   `RuntimeActivityList`；删除 `console.log` 临时实现，复制仍只使用 answer。
5. 增加迁移方案要求的 Go 单元/集成测试和前端 reducer 单元测试；加入最小 Vitest
   脚本与 lockfile 变更。
6. 运行并记录提交后的真实命令：
   `go test ./...`、`python -m pytest`、frontend unit、lint、build、
   `git diff --check`。
7. 更新迁移进度文档，并使用 Handoff 模板提交
   `collaboration/handoffs/TASK-002-round-2.md`；完整记录三个 Required Skills 如何
   影响信息架构、交互、视觉和可访问性。

## 下一步

Grok 只修复本 Review 列出的 TASK-002 问题，提交 Round-2 Handoff 后停止。不得启动
TASK-003、合并 main、修改生产配置或扩大到 Citation/Skill/统一模式。
