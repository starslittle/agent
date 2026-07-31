# P0 Runtime 自动验收

统一入口按 Product Run 风险组织 Python、Go、前端和 Compose 门禁，并生成不含命令
输出、用户内容、Prompt 或环境变量值的 JSON 与 Markdown 报告。

## 本地分层验收

```powershell
python scripts/run_p0_acceptance.py --profile local
```

报告写入被 Git 忽略的 `reports/p0-runtime-acceptance/report.json` 和 `summary.md`。
未配置隔离 PostgreSQL 时，相关套件与风险显示为 `skipped`，整体结果为 `partial`；
这不等于通过完整 P0 门禁。任何已执行命令失败都会返回非零退出码。
Compose 仅做配置解析，入口会注入固定测试占位值满足必填插值，不读取真实 Secret。

## 完整验收

先为隔离测试库设置 `TEST_DATABASE_URL`，并确认 Docker daemon 可用，再执行：

```powershell
$env:TEST_DATABASE_URL = "<isolated-test-database>"
python scripts/run_p0_acceptance.py --profile full
Remove-Item Env:TEST_DATABASE_URL
```

`full` 模式要求所有套件和风险均为 `passed`；`failed`、`skipped` 或 `not-run` 均返回
非零退出码。入口会先对该隔离测试库执行幂等 Go migration，再运行 Python 与 Go
PostgreSQL 套件；Go 的全包单元测试会显式移除数据库变量，数据库集成测试仅在专用
套件中执行一次。不得把生产或共享开发库填入 `TEST_DATABASE_URL`。真实 Provider
不是前提。

## 状态语义

- `passed`：套件实际执行且退出码为 0；
- `failed`：套件实际执行但失败或超时；
- `skipped`：缺少明确声明的外部测试条件，例如隔离 PostgreSQL；
- `not-run`：本机缺少命令或命令无法启动；
- `partial`：可运行层通过，但至少一层被跳过。

风险与可定位测试的对应关系维护在 `scripts/p0_runtime_matrix.json`。报告仅保存固定的
测试标识、commit、分支、耗时和状态；完整测试输出只出现在当前终端。
