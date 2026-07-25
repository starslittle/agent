# 登录与身份架构

## 当前边界

登录属于产品基础设施，由 Go 公网服务统一负责。Python Agent 不是身份源，
也不接受浏览器直接访问。

```text
Browser
  ├─ 注册 / 登录 / Session / 退出 ──> Go API ──> PostgreSQL
  └─ 带 Session + CSRF 的聊天请求 ──> Go API
                                      └─ HMAC 签名 ──> Python Agent
```

- PostgreSQL 是用户、登录身份、密码凭据和 Session 的唯一事实源。
- 浏览器只持有 HttpOnly、SameSite=Lax 的不透明 Session Cookie。
- Session Token 在数据库中只保存 SHA-256 摘要。
- CSRF Token 由 Session 接口返回，状态变更请求放入
  `X-CSRF-Token`。
- 密码使用 Argon2id；数据库不保存明文密码。
- Go 只向 Python 发送已验证的用户 ID，并对请求体、用户、时间戳和请求 ID
  做 HMAC-SHA256 签名。
- Go 不向 Python 转发浏览器 Cookie、Authorization 或伪造的身份请求头。

## 数据模型

- `app_core.users`：产品用户主体与状态。
- `app_core.auth_identities`：登录身份；当前 provider 为 `password`，后续可增加
  Google、GitHub、微信等身份而不修改用户主表。
- `app_core.password_credentials`：Argon2id 密码摘要。
- `app_core.sessions`：可撤销的服务端 Session、CSRF Token 和过期时间。
- `app_core.login_audit_logs`：成功/失败登录审计。

数据库迁移由 Go 启动时执行，文件位于
`go-backend/internal/platform/postgres/migrations/`。

## 请求流程

1. 注册或登录成功后，Go 创建服务端 Session，返回用户和 CSRF Token，并设置
   HttpOnly Cookie。
2. 页面刷新时，前端调用 `GET /api/v1/session` 恢复用户与 CSRF Token。
3. `/query_stream` 和退出请求必须同时通过 Origin、Session 与 CSRF 校验。
4. Go 为通过认证的 Agent 请求生成内部签名；Python 校验签名和 90 秒时间窗。
5. 退出时删除数据库 Session，并清除浏览器 Cookie。

## 生产要求

- `COOKIE_SECURE=true`，站点全程 HTTPS。
- `PUBLIC_ORIGINS` 只列出实际前端 Origin，不使用 `*`。
- `INTERNAL_AGENT_SECRET` 至少 32 个随机字符，通过平台 Secret 注入并定期轮换。
- Go 是唯一公网入口；Python 和 PostgreSQL 只允许内部网络访问。
- 多实例部署前，把当前进程内登录限流迁到 Redis，以共享失败计数。
- 邮件验证、密码重置、全设备退出和管理员封禁属于下一阶段；实现前不要在
  前端展示不可用入口。

## 可扩展方向

`auth_identities` 已把“用户”与“登录方式”分离。接入 OAuth/OIDC 时，应继续由
Go 完成回调、state/nonce/PKCE 校验，并把外部身份绑定到现有用户；不要把外部
Access Token 暴露给前端或 Python Agent。

后续会话列表、用户设置、订阅和权限系统都应引用 `users.id`。建议业务表统一
包含 `user_id`，并由 Go 从已验证 Session 注入，不接受浏览器提交的所有者 ID。
