import React from "react";
import ChatContainer from "@/components/chat/ChatContainer";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { SidebarProvider } from "@/components/ui/sidebar";
import { useAuth } from "@/auth/AuthProvider";
import { LogOut } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const Index = () => {
  const { user, logout } = useAuth();

  return (
    <SidebarProvider>
      <div className="h-screen w-full bg-background flex overflow-hidden">
        <ChatSidebar />

        <div className="flex-1 flex flex-col min-w-0">
          <header className="border-b flex-shrink-0">
            <div className="container py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className="grid h-9 w-9 place-items-center rounded-full bg-card border border-border shadow-sm"
                  aria-label="奇点AI Logo"
                >
                  <span className="bg-gradient-to-tr from-primary to-accent bg-clip-text text-transparent text-sm font-bold">
                    奇
                  </span>
                </div>
                <span className="text-lg font-semibold">奇点AI</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="hidden text-right sm:block">
                  <p className="text-sm font-medium">{user?.display_name}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                </div>
                <ThemeToggle />
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="grid h-9 w-9 place-items-center rounded-xl border bg-background text-muted-foreground transition hover:border-primary/30 hover:bg-primary/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="退出登录"
                  title="退出登录"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </header>

          <main className="flex-1 overflow-hidden w-full relative">
            <ChatContainer />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
};

export default Index;
