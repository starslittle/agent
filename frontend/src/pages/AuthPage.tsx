import { useMemo, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { QidianMark, QidianWordmark } from "@/brand/QidianMark";

type FieldErrors = Partial<Record<"displayName" | "email" | "password", string>>;

export default function AuthPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const isRegister = location.pathname === "/register";
  const { user, loading, login, register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [requestError, setRequestError] = useState("");
  const displayNameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const destination = useMemo(() => {
    const state = location.state as { from?: string } | null;
    return state?.from?.startsWith("/") ? state.from : "/";
  }, [location.state]);

  if (!loading && user) return <Navigate to="/" replace />;

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (isRegister && !displayName.trim()) errors.displayName = "请输入你的称呼";
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) errors.email = "请输入有效的邮箱地址";
    if (password.length < 12) errors.password = "密码至少需要 12 个字符";
    return errors;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRequestError("");
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      requestAnimationFrame(() => {
        if (errors.displayName) displayNameRef.current?.focus();
        else if (errors.email) emailRef.current?.focus();
        else passwordRef.current?.focus();
      });
      return;
    }

    setSubmitting(true);
    try {
      if (isRegister) {
        await register({ email: email.trim(), password, display_name: displayName.trim() });
      } else {
        await login({ email: email.trim(), password });
      }
      navigate(destination, { replace: true });
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "操作没有完成，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-dvh bg-background text-foreground">
      <a href="#auth-form" className="skip-link">跳到登录表单</a>
      <header className="flex min-h-[4.5rem] items-center justify-between border-b border-border px-5 sm:px-8">
        <Link to="/" className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="返回工作区预览">
          <QidianWordmark />
        </Link>
        <Link
          to="/"
          className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          查看工作区
        </Link>
      </header>

      <section className="mx-auto grid min-h-[calc(100dvh-4.5rem)] max-w-6xl items-center gap-12 px-5 py-10 lg:grid-cols-[1fr_28rem] lg:px-8">
        <div className="hidden max-w-xl lg:block">
          <QidianMark className="h-20 w-20" />
          <p className="mt-7 text-xs font-semibold tracking-[0.16em] text-primary">启点工作空间</p>
          <p className="mt-4 text-5xl font-semibold leading-[1.12] tracking-[-0.045em]">
            让每次对话，<br />都有清晰的下一步。
          </p>
          <p className="mt-6 max-w-md text-base leading-8 text-muted-foreground">
            一个统一助手，根据你的明确选择或意图调用专业 Skill。运行依据、来源与结果都留在同一个工作区。
          </p>
        </div>

        <div id="auth-form" className="mx-auto w-full max-w-md scroll-mt-6">
          <div className="mb-7 lg:hidden">
            <QidianMark className="h-14 w-14" />
          </div>
          <p className="text-xs font-semibold tracking-[0.14em] text-primary">
            {isRegister ? "创建启点账号" : "进入启点工作区"}
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em]">
            {isRegister ? "从这里开始" : "欢迎回来"}
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {isRegister ? "创建账号后开始你的第一段对话。" : "登录后继续已有对话和 Agent Run。"}
          </p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit} noValidate>
            {isRegister && (
              <div>
                <label htmlFor="display-name" className="text-xs font-medium">称呼</label>
                <input
                  ref={displayNameRef}
                  id="display-name"
                  name="display_name"
                  type="text"
                  autoComplete="name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  aria-invalid={Boolean(fieldErrors.displayName)}
                  aria-describedby={fieldErrors.displayName ? "display-name-error" : undefined}
                  className="mt-2 h-12 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-4 focus:ring-ring/15"
                  placeholder="希望启点怎样称呼你"
                />
                {fieldErrors.displayName && <p id="display-name-error" className="mt-1.5 text-xs text-destructive">{fieldErrors.displayName}</p>}
              </div>
            )}

            <div>
              <label htmlFor="email" className="text-xs font-medium">邮箱</label>
              <input
                ref={emailRef}
                id="email"
                name="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(fieldErrors.email)}
                aria-describedby={fieldErrors.email ? "email-error" : undefined}
                className="mt-2 h-12 w-full rounded-xl border border-input bg-background px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-4 focus:ring-ring/15"
                placeholder="name@example.com"
              />
              {fieldErrors.email && <p id="email-error" className="mt-1.5 text-xs text-destructive">{fieldErrors.email}</p>}
            </div>

            <div>
              <label htmlFor="password" className="text-xs font-medium">密码</label>
              <div className="relative mt-2">
                <input
                  ref={passwordRef}
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={fieldErrors.password ? "password-error" : "password-help"}
                  className="h-12 w-full rounded-xl border border-input bg-background px-3 pr-12 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-4 focus:ring-ring/15"
                  placeholder="至少 12 个字符"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  className="absolute inset-y-0 right-0 grid w-12 place-items-center rounded-r-xl text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
              {fieldErrors.password ? (
                <p id="password-error" className="mt-1.5 text-xs text-destructive">{fieldErrors.password}</p>
              ) : (
                <p id="password-help" className="mt-1.5 text-[11px] text-muted-foreground">至少 12 个字符</p>
              )}
            </div>

            {requestError && (
              <div role="alert" className="rounded-xl border border-destructive/25 bg-destructive/5 px-3 py-3 text-xs text-destructive">
                {requestError}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || loading}
              className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-[background-color,transform,opacity] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 disabled:cursor-not-allowed disabled:opacity-55 motion-reduce:transform-none"
            >
              {submitting || loading ? <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <ArrowRight className="h-4 w-4" aria-hidden="true" />}
              {submitting ? "正在提交" : isRegister ? "创建账号" : "登录"}
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            {isRegister ? "已有账号？" : "还没有账号？"}{" "}
            <Link to={isRegister ? "/login" : "/register"} className="font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {isRegister ? "直接登录" : "创建账号"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
