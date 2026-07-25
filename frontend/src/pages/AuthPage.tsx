import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
} from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";

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
  const [error, setError] = useState("");

  const destination = useMemo(() => {
    const state = location.state as { from?: string } | null;
    return state?.from || "/";
  }, [location.state]);

  if (!loading && user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password.length < 12) {
      setError("密码至少需要 12 个字符");
      return;
    }
    setSubmitting(true);
    try {
      if (isRegister) {
        await register({ email, password, display_name: displayName });
      } else {
        await login({ email, password });
      }
      navigate(destination, { replace: true });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "操作没有完成");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-[#f7f8fc] text-foreground dark:bg-[#080a13]">
      <div
        className="pointer-events-none absolute inset-0 opacity-90 dark:opacity-70"
        aria-hidden="true"
      >
        <div className="absolute left-1/2 top-[42%] h-[32rem] w-[48rem] -translate-x-1/2 -translate-y-1/2 rotate-[-9deg] rounded-[50%] border border-violet-300/25 dark:border-violet-400/10" />
        <div className="absolute left-1/2 top-[42%] h-[24rem] w-[38rem] -translate-x-1/2 -translate-y-1/2 rotate-[12deg] rounded-[50%] border border-blue-300/20 dark:border-blue-400/10" />
        <div className="absolute left-1/2 top-[38%] h-80 w-80 -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-300/15 blur-3xl dark:bg-violet-600/10" />
      </div>

      <header className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-5 py-5 sm:px-8 sm:py-7">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-[0.9rem] border border-violet-200/80 bg-white/80 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/5">
            <span className="bg-gradient-to-tr from-violet-600 to-blue-500 bg-clip-text text-sm font-bold text-transparent dark:from-violet-300 dark:to-blue-300">
              奇
            </span>
          </div>
          <div>
            <p className="text-[15px] font-semibold tracking-tight">奇点AI</p>
            <p className="text-[10px] tracking-[0.2em] text-muted-foreground">
              QIDIAN INTELLIGENCE
            </p>
          </div>
        </div>
        <p className="hidden text-xs text-muted-foreground sm:block">
          对话与任务，回到同一个工作空间
        </p>
      </header>

      <section className="relative z-10 mx-auto flex min-h-screen w-full max-w-[29rem] flex-col justify-center px-5 pb-12 pt-28 sm:px-4 sm:pb-16">
        <div className="animate-in fade-in-0 slide-in-from-bottom-3 duration-500 motion-reduce:animate-none motion-reduce:transition-none">
          <div className="mb-6 text-center">
            <div className="relative mx-auto mb-6 h-16 w-16" aria-hidden="true">
              <div className="absolute inset-[3px] rotate-[-18deg] rounded-[50%] border border-violet-400/40" />
              <div className="absolute inset-[10px] rotate-[22deg] rounded-[50%] border border-blue-400/35" />
              <div className="absolute inset-0 animate-[spin_18s_linear_infinite] rounded-[50%] border border-transparent border-t-violet-500/70 motion-reduce:animate-none" />
              <div className="absolute left-1/2 top-1/2 grid h-9 w-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#111526] text-xs font-bold text-white shadow-[0_10px_30px_-10px_rgba(91,33,182,0.75)] dark:bg-white dark:text-[#111526]">
                奇
              </div>
            </div>

            <p className="mb-3 text-[11px] font-semibold tracking-[0.18em] text-primary">
              {isRegister ? "创建工作空间账号" : "进入你的工作空间"}
            </p>
            <h1 className="text-[2.35rem] font-semibold leading-tight tracking-[-0.045em] text-foreground sm:text-[2.65rem]">
              {isRegister ? "从这里开始" : "欢迎回来"}
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-muted-foreground">
              {isRegister
                ? "创建账号后，你的对话与任务会安全地归于同一个工作空间。"
                : "登录后继续上次的对话、研究与智能体任务。"}
            </p>
          </div>

          <div className="rounded-[1.75rem] border border-white/80 bg-white/85 p-5 shadow-[0_24px_80px_-36px_rgba(31,41,70,0.3)] backdrop-blur-xl sm:p-7 dark:border-white/10 dark:bg-white/[0.055] dark:shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
            <form className="space-y-5" onSubmit={handleSubmit}>
            {isRegister && (
              <label className="block space-y-2">
                <span className="text-sm font-medium text-foreground">称呼</span>
                <input
                  id="display-name"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  autoComplete="name"
                  maxLength={80}
                  placeholder="你希望我们如何称呼你"
                  className="h-12 w-full rounded-xl border border-input bg-background/70 px-4 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/70 focus:border-primary focus:ring-4 focus:ring-primary/15"
                />
              </label>
            )}

            <label className="block space-y-2">
              <span className="text-sm font-medium text-foreground">邮箱</span>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                placeholder="name@example.com"
                className="h-12 w-full rounded-xl border border-input bg-background/70 px-4 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/70 focus:border-primary focus:ring-4 focus:ring-primary/15"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-foreground">密码</span>
              <span className="relative block">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={12}
                  maxLength={128}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  placeholder={isRegister ? "至少 12 个字符" : "输入你的密码"}
                  className="h-12 w-full rounded-xl border border-input bg-background/70 px-4 pr-12 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/70 focus:border-primary focus:ring-4 focus:ring-primary/15"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </span>
            </label>

            {error && (
              <div
                role="alert"
                className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="group flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#121629] px-5 text-sm font-semibold text-white shadow-[0_16px_35px_-20px_rgba(18,22,41,0.8)] transition hover:-translate-y-0.5 hover:bg-[#1d2340] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25 disabled:pointer-events-none disabled:opacity-60 motion-reduce:transform-none dark:bg-white dark:text-[#121629] dark:hover:bg-white/90"
            >
              {submitting ? (
                <><LoaderCircle className="h-4 w-4 animate-spin" />正在处理</>
              ) : (
                <>{isRegister ? "创建账号" : "登录"}<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
              )}
            </button>
            </form>
          </div>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            {isRegister ? "已经有账号？" : "还没有账号？"}
            <Link
              to={isRegister ? "/login" : "/register"}
              className="ml-2 font-semibold text-primary underline-offset-4 hover:underline"
            >
              {isRegister ? "直接登录" : "现在注册"}
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}
