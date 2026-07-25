import React, { useState } from "react";
import ChatContainer from "@/components/chat/ChatContainer";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useAuth } from "@/auth/AuthProvider";
import { LogOut, Sparkles } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const Index = () => {
  const { user, logout } = useAuth();
  const [chatKey, setChatKey] = useState(0);

  return (
    <SidebarProvider>
      <div className="flex h-screen w-full overflow-hidden bg-[#f5f7fb] dark:bg-[#080a13]">
        <ChatSidebar onNewChat={() => setChatKey((key) => key + 1)} />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="z-20 flex h-[4.5rem] flex-shrink-0 items-center border-b border-border/60 bg-background/75 px-4 backdrop-blur-xl sm:px-6">
            <div className="flex w-full items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <SidebarTrigger className="h-9 w-9 rounded-xl border border-border/70 bg-background/80 text-muted-foreground hover:bg-muted" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h1 className="truncate text-sm font-semibold sm:text-base">新的对话</h1>
                    <span className="hidden items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-700 sm:inline-flex dark:text-emerald-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      在线
                    </span>
                  </div>
                  <p className="mt-0.5 hidden truncate text-xs text-muted-foreground sm:block">
                    与奇点AI一起梳理问题、研究信息和执行任务
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden items-center gap-2 rounded-full border border-border/70 bg-background/70 py-1.5 pl-2 pr-3 shadow-sm sm:flex">
                  <div className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-tr from-violet-500 to-blue-500 text-[11px] font-semibold text-white">
                    {user?.display_name?.trim().slice(0, 1) || "奇"}
                  </div>
                  <div className="max-w-36 text-left">
                    <p className="truncate text-xs font-medium">{user?.display_name}</p>
                    <p className="truncate text-[10px] text-muted-foreground">{user?.email}</p>
                  </div>
                </div>
                <ThemeToggle />
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="grid h-9 w-9 place-items-center rounded-xl border border-border/70 bg-background/80 text-muted-foreground transition hover:border-primary/30 hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="退出登录"
                  title="退出登录"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </header>

          <main className="relative w-full flex-1 overflow-hidden">
            <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
              <div className="absolute left-1/2 top-[38%] h-[34rem] w-[48rem] -translate-x-1/2 -translate-y-1/2 rotate-[-8deg] rounded-[50%] border border-violet-300/15 dark:border-violet-400/[0.06]" />
              <div className="absolute left-1/2 top-[38%] h-[24rem] w-[38rem] -translate-x-1/2 -translate-y-1/2 rotate-[11deg] rounded-[50%] border border-blue-300/15 dark:border-blue-400/[0.06]" />
              <div className="absolute left-1/2 top-[35%] h-72 w-72 -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-300/10 blur-3xl dark:bg-violet-600/[0.06]" />
            </div>
            <ChatContainer key={chatKey} />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
};

export default Index;
