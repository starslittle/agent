import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Bot,
  ChevronUp,
  FolderClosed,
  LogIn,
  LogOut,
  LoaderCircle,
  MessageSquare,
  Moon,
  ShieldCheck,
  Sparkles,
  Sun,
} from "lucide-react";
import { useTheme } from "next-themes";

import { useAuth } from "@/auth/AuthProvider";
import { QidianWordmark } from "@/brand/QidianMark";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { ConversationSearchDialog } from "@/components/workspace/ConversationSearchDialog";
import { ChatSidebarContent } from "@/components/chat/ChatSidebar";
import { useWorkspaceConversations } from "@/components/workspace/workspace-conversations-context";

const navigationLinkClass =
  "flex min-h-11 items-center gap-2.5 rounded-lg px-3 text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring sm:min-h-9";

export function WorkspaceLoadingScreen({ label = "正在准备工作区…" }: { label?: string }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-background px-5 text-foreground">
      <div className="flex flex-col items-center gap-5" role="status" aria-live="polite">
        <QidianWordmark />
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {label}
        </span>
      </div>
    </main>
  );
}

export function WorkspaceThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={isDark ? "切换到亮色模式" : "切换到暗色模式"}
    >
      {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}

function WorkspaceNav() {
  const { user } = useAuth();
  const { startNewChat } = useWorkspaceConversations();
  const location = useLocation();
  const newChatActive = location.pathname === "/";
  const runsActive = location.pathname.startsWith("/agent-runs");
  const spaceActive = location.pathname.startsWith("/space");
  const skillsActive = location.pathname.startsWith("/skills");
  const internalActive = location.pathname.startsWith("/internal/agent-runs");

  return (
    <nav className="space-y-0.5" aria-label="工作区导航">
      <button
        type="button"
        onClick={startNewChat}
        aria-current={newChatActive ? "page" : undefined}
        className={cn(
          "w-full text-left",
          navigationLinkClass,
          newChatActive
            ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
            : "text-muted-foreground",
        )}
      >
        <MessageSquare className="h-4 w-4" aria-hidden="true" />
        新对话
      </button>
      <Link
        to="/agent-runs"
        aria-current={runsActive ? "page" : undefined}
        className={cn(
          navigationLinkClass,
          runsActive
            ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
            : "text-muted-foreground",
        )}
      >
        <Bot className="h-4 w-4" aria-hidden="true" />
        Agent Runs
      </Link>
      <Link
        to="/space"
        aria-current={spaceActive ? "page" : undefined}
        className={cn(
          navigationLinkClass,
          spaceActive
            ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
            : "text-muted-foreground",
        )}
      >
        <FolderClosed className="h-4 w-4" aria-hidden="true" />
        我的空间
      </Link>
      <Link
        to="/skills"
        aria-current={skillsActive ? "page" : undefined}
        className={cn(
          navigationLinkClass,
          skillsActive
            ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
            : "text-muted-foreground",
        )}
      >
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        Skills
      </Link>
      {user?.role === "observability_admin" && (
        <Link
          to="/internal/agent-runs"
          aria-current={internalActive ? "page" : undefined}
          className={cn(
            navigationLinkClass,
            internalActive
              ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
              : "text-muted-foreground",
          )}
        >
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          内部观测
        </Link>
      )}
    </nav>
  );
}

function WorkspaceAccountMenu() {
  const { user, logout } = useAuth();
  if (!user) return null;

  const displayName = user.display_name?.trim() || "启点用户";
  const initial = displayName.slice(0, 1);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex min-h-12 w-full items-center gap-2.5 rounded-xl border border-border bg-background/60 px-3 text-left transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring sm:min-h-11"
          aria-label="打开账户菜单"
        >
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
            {initial}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{displayName}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{user.email}</span>
          </span>
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" sideOffset={8} className="w-56">
        <DropdownMenuLabel className="min-w-0">
          <span className="block truncate text-sm font-medium">{displayName}</span>
          <span className="mt-1 block truncate text-xs font-normal text-muted-foreground">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="min-h-11" onSelect={() => void logout()}>
          <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function WorkspaceSidebar({ content }: { content?: ReactNode }) {
  const { user } = useAuth();
  const {
    conversations,
    loading,
    activeConversationId,
    selectConversation,
    renameConversation,
    deleteConversation,
  } = useWorkspaceConversations();

  const conversationContent = user ? (
    <ChatSidebarContent
      conversations={conversations}
      activeConversationId={activeConversationId}
      onSelect={selectConversation}
      onRename={(conversation) => void renameConversation(conversation)}
      onDelete={(conversation) => void deleteConversation(conversation)}
      loading={loading}
    />
  ) : null;

  return (
    <Sidebar variant="sidebar" className="border-r border-sidebar-border bg-sidebar">
      <SidebarHeader className="gap-3 px-4 pb-2 pt-4">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <Link
            to="/"
            className="min-w-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
            aria-label="返回启点工作区"
          >
            <QidianWordmark />
          </Link>
          {user && <ConversationSearchDialog />}
        </div>
        <WorkspaceNav />
      </SidebarHeader>
      <SidebarContent className="overflow-hidden">{content ?? conversationContent}</SidebarContent>
      {user && (
        <SidebarFooter className="px-4 pb-3 pt-2">
          <WorkspaceAccountMenu />
        </SidebarFooter>
      )}
    </Sidebar>
  );
}

interface WorkspaceShellProps {
  children: ReactNode;
  title: string;
  subtitle: string;
  mainId: string;
  skipLabel?: string;
  sidebarContent?: ReactNode;
  headerActions?: ReactNode;
  mainClassName?: string;
}

export function WorkspaceShell({
  children,
  title,
  subtitle,
  mainId,
  skipLabel = "跳到主要内容",
  sidebarContent,
  headerActions,
  mainClassName,
}: WorkspaceShellProps) {
  const { user } = useAuth();

  return (
    <SidebarProvider className="h-dvh min-h-0 overflow-hidden bg-background text-foreground">
      <a href={`#${mainId}`} className="skip-link">{skipLabel}</a>
      <WorkspaceSidebar content={sidebarContent} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="z-20 flex min-h-[4.5rem] shrink-0 items-center justify-between border-b border-border bg-background px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <SidebarTrigger
              className="h-11 w-11 shrink-0 rounded-xl border border-border/70 bg-background/80 text-muted-foreground hover:bg-muted"
              aria-label="切换侧栏"
            />
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold sm:text-base">{title}</h1>
              <p className="mt-0.5 hidden truncate text-xs text-muted-foreground sm:block">{subtitle}</p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {headerActions}
            <WorkspaceThemeToggle />
            {!user && (
              <Link
                to="/login"
                className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-[background-color,transform] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 motion-reduce:transform-none"
              >
                登录
                <LogIn className="h-4 w-4" aria-hidden="true" />
              </Link>
            )}
          </div>
        </header>

        <main id={mainId} className={cn("min-h-0 flex-1 overflow-hidden", mainClassName)}>
          {children}
        </main>
      </div>
    </SidebarProvider>
  );
}
