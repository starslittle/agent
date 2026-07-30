# 协作协议

## 1. 权威来源

执行者按以下顺序解决冲突：

```text
用户最新决定
→ AGENTS.md
→ 产品范围文档
→ 目标架构
→ accepted ADR
→ 当前 Task
→ 当前 Review
```

Task可以限制实现范围；不能静默推翻产品、架构或ADR。

## 2. Task状态

- `draft`：方案尚未冻结，不得执行；
- `ready`：允许指定执行者开始；
- `blocked`：缺少产品决定、权限或前置条件；
- `accepted`：Reviewer确认完成；
- `superseded`：被新Task替代。

Task文件只由Planner/Reviewer维护。

每个Task必须填写`source_todos`，引用原始迁移TODO或产品文档章节，并说明本Task是
完整解决还是部分承接。这样可以防止历史遗留漏项、重复实现或在迁移中失去原始
验收语义。

涉及前端页面、视觉组件、布局或用户交互的Task还必须填写：

```yaml
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
```

三个Skill必须全部可读并在实现前使用。缺少任意一个时，执行者写阻塞Handoff并停止；
不能自行省略或替换。

## 3. 单个 Task 执行

Grok执行一个Task时：

1. 核对Task ID、状态、执行者、依赖、所属 `business_round` 和基准提交；
2. 确认所属业务轮次已经获得用户授权且处于 `ready` 或 `in_progress`；
3. 阅读所属Round和Task引用的文档；
4. 检查工作树，保留不相关修改；
5. 只修改 `allowed_paths`；
6. 完成代码、测试和必要的直接文档；
7. 完成静态检查、单元测试、模块级集成测试和Task指定的执行者验证；
8. 在Handoff记录所有`required_skills`的读取和实际应用；
9. 写入 `handoffs/<task-id>-round-N.md`；
10. 停止，不开始下一个需要Review的Task。

无法继续时也必须写Handoff，并将状态标为 `blocked`。

## 4. Handoff状态

- `ready_for_review`
- `blocked`
- `failed`

Handoff必须使用模板，不能只写“完成”。

## 5. Review状态

- `accepted`
- `changes_requested`
- `blocked_on_product_decision`

Review问题按严重度：

- P0：安全、数据损坏、错误状态机、核心架构违反；
- P1：功能、契约或必要测试缺失；
- P2：非阻塞的质量和可维护性问题。

Grok只能修复Review中列出的事项；新范围必须形成Task修订或新Task。

## 6. 验证责任

验证分为两个独立层级：

### Grok：代码层验证

- 静态检查、类型检查和构建；
- 单元测试；
- 模块级集成测试；
- Task明确要求执行者运行的确定性验证；
- 在Handoff中记录命令、结果、失败项和已知风险。

Grok可以运行已经固化的自动化E2E作为辅助证据，但不能用自己的运行结果替代Codex的
独立产品级验收，也不能自行把Task标记为`accepted`。

### Codex：验收层验证

- 对照Task审查真实diff、接口契约和架构边界；
- 判断测试覆盖与回归风险；
- 对用户可见或跨服务Task独立执行产品级E2E；
- 涉及真实页面或桌面交互时，使用Browser / Computer Use模拟用户旅程；
- 将实际观察、截图或其他必要证据写入Review；
- 失败时集中输出`changes_requested`，由Grok进入下一轮修复。

Task必须声明：

```yaml
codex_e2e: required | not_applicable
```

前端交互、跨服务调用、状态机、用户数据写入、Skill完整调用链默认必须为`required`。
只有纯内部且尚未接入产品路径的基础能力可以标记`not_applicable`，并在Task与Review中
说明原因。只有Codex完成独立审查，并通过必需E2E或确认其不适用后，才能输出
`accepted`。

### 验收时机

不采用“所有Task做完后一次性验收”。默认节奏是：

1. Grok完成当前Task后立即运行Task规定的代码层验证并提交Handoff；
2. Codex立即审查当前Task；`codex_e2e: required`时执行与当前边界匹配的最小独立
   E2E；
3. 当前Task只有在`accepted`后才解除其下游依赖；
4. 每个业务轮次完成后执行一次跨Task完整回归；
5. TASK-024负责秋招MVP完整12步产品E2E，TASK-027负责发布准备门禁。

即时验收不等于每个Task都重复完整产品E2E。验证深度按当前Task风险和可观察边界
确定；完整用户链路留在里程碑Task集中执行。后续集成发现已接受Task存在回归时，保留
原Review历史，通过新一轮修复Task或当前集成Task的`changes_requested`处理。

## 7. 业务交付轮次

业务轮次定义和状态见 [`rounds/README.md`](rounds/README.md)。

### 开始

业务轮次只有在用户明确授权后才能从`draft`进入`ready`。开始前Codex必须冻结：

- 本轮业务结果、Task清单和执行顺序；
- Round base commit；
- 完整用户旅程、失败场景和上轮回归范围；
- 服务端能力控制或等价流量切换机制；
- Migration兼容、数据保留和依赖闭包；
- 回滚步骤、停止条件和成功判据。

一次授权只覆盖当前业务轮次，不覆盖下一轮、生产发布或破坏性数据操作。

### 执行与完成

轮次内仍逐Task执行和即时Review。所有Task都`accepted`后，Round进入`acceptance`，
由Codex：

1. 使用Browser / Computer Use执行Round规定的完整业务旅程；
2. 回归上一轮核心能力；
3. 验证服务端能力关闭后前端入口同步消失且API拒绝新请求；
4. 在非生产环境演练局部回滚和重新启用；
5. 检查旧行为在新Schema保留时仍可工作；
6. 使用`templates/round-acceptance-template.md`记录证据。

完成后记录accepted commit，可选准备稳定Tag，但未经用户明确要求不自动Commit、
Tag、Push或部署。Round标记`accepted`后必须停止并等待下一轮授权。

### 局部回滚

默认顺序：

```text
关闭当前业务能力
→ 切回上一轮accepted部署/提交
→ 必要时回退当前轮代码
```

- 能力控制必须由服务端执行，前端隐藏不是安全边界；
- 上层能力可以独立关闭；关闭底层时必须同时关闭依赖它的上层能力；
- Migration采用Expand–Migrate–Contract；
- 常规回滚保留新Schema和已写入数据，不执行破坏性Down Migration；
- 不删除Wiki Revision、Decision、Review、Run或用户确认数据来制造回滚成功；
- destructive Contract和兼容代码删除必须形成单独Task；
- 生产回滚仍需用户明确授权。

## 8. 分支与工作区

默认分支名：

```text
grok/<task-id>-<short-name>
```

推荐为Grok创建仓库外部的同级worktree，避免与主工作区混写。例如：

```text
/Users/bytedance/other/qidianAgent
/Users/bytedance/other/qidianAgent-grok-task-001
```

协作文件随Git分支传递，不在仓库内嵌套另一个worktree。

## 9. Review Gate

默认：

```yaml
review_gate: required
```

只有互不依赖、低风险、机械化任务才可以由Task显式设置：

```yaml
review_gate: batch
```

数据库Migration、协议、状态机、权限、记忆、Skill路由和生产配置永远需要
`required`。

## 10. 禁止内容

Task、Handoff和Review中不得保存：

- API Key和Secret；
- Cookie、Authorization和数据库连接串；
- 完整用户内容；
- 未脱敏生产日志；
- 模型隐式思维链；
- 与Task无关的大段输出。
