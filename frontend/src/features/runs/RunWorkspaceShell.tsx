import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bot, LogOut, MessageSquare, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { QidianWordmark } from "@/brand/QidianMark";
import { useAuth } from "@/auth/AuthProvider";
import { cn } from "@/lib/utils";

function RunsThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  return (
    <button type="button" onClick={() => setTheme(isDark ? "light" : "dark")} className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={isDark ? "切换到亮色模式" : "切换到暗色模式"}>
      {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}

export function RunWorkspaceShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const runsActive = location.pathname.startsWith("/agent-runs");

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <a href="#runs-main" className="skip-link">跳到运行内容</a>
      <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar p-5 lg:flex">
        <QidianWordmark />
        <nav className="mt-10 space-y-1" aria-label="工作区导航">
          <Link to="/" className="flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring">
            <MessageSquare className="h-4 w-4" aria-hidden="true" />对话
          </Link>
          <Link to="/agent-runs" aria-current={runsActive ? "page" : undefined} className={cn("flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring", runsActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground")}>
            <Bot className="h-4 w-4" aria-hidden="true" />Agent Runs
          </Link>
        </nav>
        <div className="mt-auto rounded-xl border border-border bg-background/60 p-3">
          <p className="truncate text-xs font-medium">{user?.display_name}</p>
          <p className="mt-1 truncate text-[10px] text-muted-foreground">{user?.email}</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-[4.5rem] shrink-0 items-center justify-between border-b border-border bg-background px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="lg:hidden"><QidianWordmark /></div>
            <div className="hidden lg:block">
              <p className="text-sm font-semibold">Agent Runs</p>
              <p className="mt-0.5 text-xs text-muted-foreground">查看我的任务实际发生了什么</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/" className="hidden min-h-11 items-center gap-2 rounded-xl px-3 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex">
              <MessageSquare className="h-4 w-4" aria-hidden="true" />对话
            </Link>
            <RunsThemeToggle />
            <button type="button" onClick={() => void logout()} className="grid h-11 w-11 place-items-center rounded-xl border border-border text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="退出登录">
              <LogOut className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </header>
        <main id="runs-main" className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
