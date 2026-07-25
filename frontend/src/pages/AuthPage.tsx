import { useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Orbit,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import logo from "@/assets/qidian-logo.png";

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
    <main className="min-h-screen overflow-hidden bg-background text-foreground lg:grid lg:grid-cols-[1.12fr_0.88fr]">
      <section className="relative hidden min-h-screen overflow-hidden bg-[#080b19] px-12 py-10 text-white lg:flex lg:flex-col">
        <div className="absolute -left-24 top-1/4 h-80 w-80 rounded-full bg-violet-600/20 blur-3xl" />
        <div className="absolute -right-16 bottom-20 h-72 w-72 rounded-full bg-blue-500/15 blur-3xl" />
        <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(circle_at_center,rgba(255,255,255,.22)_1px,transparent_1px)] [background-size:38px_38px]" />

        <div className="relative z-10 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl border border-white/10 bg-white/10">
            <img src={logo} alt="" className="h-7 w-7 object-contain" />
          </div>
          <div>
            <p className="text-lg font-semibold tracking-tight">奇点AI</p>
            <p className="text-xs tracking-[0.24em] text-white/45">QIDIAN INTELLIGENCE</p>
          </div>
        </div>

        <div className="relative z-10 my-auto max-w-2xl pb-16">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-violet-300/20 bg-violet-400/10 px-4 py-2 text-sm text-violet-100">
            <Orbit className="h-4 w-4" />
            你的智能工作空间
          </div>
          <h1 className="max-w-xl text-[clamp(3.4rem,6vw,6.5rem)] font-semibold leading-[0.94] tracking-[-0.055em]">
            思考，
            <span className="block bg-gradient-to-r from-violet-300 via-fuchsia-200 to-blue-300 bg-clip-text text-transparent">
              从一个奇点开始。
            </span>
          </h1>
          <p className="mt-8 max-w-lg text-lg leading-8 text-slate-300">
            登录后，你的对话、研究任务与智能体执行记录将拥有明确、安全的个人归属。
          </p>
        </div>

        <div className="relative z-10 grid grid-cols-3 gap-4 border-t border-white/10 pt-6 text-sm text-white/60">
          <span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" />服务端会话</span>
          <span className="flex items-center gap-2"><LockKeyhole className="h-4 w-4" />凭据不进浏览器存储</span>
          <span className="flex items-center gap-2"><Sparkles className="h-4 w-4" />持续扩展的 Agent</span>
        </div>
      </section>

      <section className="relative flex min-h-screen items-center justify-center px-5 py-10 sm:px-10 lg:px-16">
        <div className="absolute left-5 top-5 flex items-center gap-2 lg:hidden">
          <img src={logo} alt="" className="h-8 w-8 object-contain" />
          <span className="font-semibold">奇点AI</span>
        </div>

        <div className="w-full max-w-md animate-in fade-in-0 slide-in-from-bottom-4 duration-500 motion-reduce:animate-none motion-reduce:transition-none">
          <p className="mb-5 text-xs font-semibold tracking-[0.22em] text-primary">
            {isRegister ? "CREATE YOUR SPACE" : "WELCOME BACK"}
          </p>
          <h2 className="text-4xl font-semibold tracking-[-0.04em] text-foreground">
            {isRegister ? "创建你的账号" : "继续你的思考"}
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {isRegister
              ? "完成注册后会自动登录，稍后可以继续绑定其他身份方式。"
              : "使用你的邮箱和密码进入工作空间。"}
          </p>

          <form className="mt-9 space-y-5" onSubmit={handleSubmit}>
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
                  className="h-12 w-full rounded-2xl border border-input bg-background px-4 text-sm text-foreground outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/20"
                />
              </label>
            )}

            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">邮箱</span>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                placeholder="name@example.com"
                className="h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm outline-none transition focus:border-violet-400 focus:ring-4 focus:ring-violet-100"
              />
            </label>

            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">密码</span>
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
                  className="h-12 w-full rounded-2xl border border-input bg-background px-4 pr-12 text-sm text-foreground outline-none transition focus:border-primary focus:ring-4 focus:ring-primary/20"
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
              className="group flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-primary to-accent px-5 text-sm font-semibold text-primary-foreground shadow-[0_18px_45px_-22px_hsl(var(--primary)/0.5)] transition hover:-translate-y-0.5 hover:from-primary/90 hover:to-accent/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/30 disabled:pointer-events-none disabled:opacity-60 motion-reduce:transform-none"
            >
              {submitting ? (
                <><LoaderCircle className="h-4 w-4 animate-spin" />正在处理</>
              ) : (
                <>{isRegister ? "创建账号" : "登录"}<ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" /></>
              )}
            </button>
          </form>

          <p className="mt-7 text-center text-sm text-slate-500">
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
