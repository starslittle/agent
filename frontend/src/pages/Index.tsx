import React, { useCallback, useEffect, useState } from "react";
import ChatContainer from "@/components/chat/ChatContainer";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { useAuth } from "@/auth/AuthProvider";
import {
  deleteConversation,
  getConversation,
  listConversations,
  listMessages,
  renameConversation,
  type Conversation,
  type StoredMessage,
} from "@/lib/chat-api";
import { ArrowRight, Bot, LoaderCircle, LogOut, MessageSquare, Moon, Sparkles, Sun } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { QidianMark, QidianWordmark } from "@/brand/QidianMark";
import { useTheme } from "next-themes";

function WorkspaceThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={isDark ? "切换到亮色模式" : "切换到暗色模式"}
    >
      {isDark ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}

function WorkspacePreview() {
  return (
    <div className="flex min-h-dvh bg-background text-foreground">
      <a href="#preview-main" className="skip-link">跳到主要内容</a>
      <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-sidebar p-5 lg:flex">
        <QidianWordmark />
        <nav className="mt-10 space-y-1" aria-label="工作区预览导航">
          <div className="flex min-h-11 items-center gap-3 rounded-xl bg-sidebar-accent px-3 text-sm font-medium text-sidebar-accent-foreground">
            <MessageSquare className="h-4 w-4" aria-hidden="true" />
            对话
          </div>
          <div className="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground">
            <Bot className="h-4 w-4" aria-hidden="true" />
            Agent Runs
          </div>
        </nav>
        <div className="mt-auto rounded-xl border border-border bg-background/60 p-4">
          <p className="text-xs font-medium">登录后开始使用</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">对话和运行记录只对你的账号可见。</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-[4.5rem] items-center justify-between border-b border-border px-4 sm:px-6">
          <div className="lg:hidden"><QidianWordmark /></div>
          <div className="hidden lg:block">
            <p className="text-sm font-semibold">工作区预览</p>
            <p className="mt-0.5 text-xs text-muted-foreground">一个助手，多种专业 Skill</p>
          </div>
          <div className="flex items-center gap-2">
            <WorkspaceThemeToggle />
            <Link
              to="/login"
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-[background-color,transform] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25 motion-reduce:transform-none"
            >
              登录
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </header>

        <main id="preview-main" className="flex flex-1 items-center justify-center px-5 py-12 sm:px-8">
          <section className="w-full max-w-3xl">
            <QidianMark className="h-16 w-16" />
            <p className="mt-6 text-xs font-semibold tracking-[0.16em] text-primary">启点工作空间</p>
            <h1 className="mt-3 max-w-2xl text-3xl font-semibold tracking-[-0.04em] sm:text-5xl sm:leading-[1.12]">
              从一个问题开始，<br className="hidden sm:block" />把思考推进到下一步。
            </h1>
            <p className="mt-5 max-w-xl text-sm leading-7 text-muted-foreground sm:text-base">
              默认直接对话；需要时明确选择深度研究或命理分析。每次运行都保留真实的 Skill 来源和过程记录。
            </p>

            <div className="mt-9 grid gap-3 lg:grid-cols-3">
              {[
                ["直接对话", "自然输入，不预设能力"],
                ["深度研究", "检索、核验并综合信息"],
                ["命理分析", "明确选择后再开始"],
              ].map(([title, description], index) => (
                <div key={title} className="rounded-2xl border border-border bg-card p-4">
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-primary/10 text-primary">
                    {index === 0 ? <MessageSquare className="h-4 w-4" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />}
                  </span>
                  <h2 className="mt-5 text-sm font-semibold">{title}</h2>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 flex items-center gap-3 border-t border-border pt-6">
              <Link to="/login" className="text-sm font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                登录后进入工作区
              </Link>
              <span className="text-xs text-muted-foreground">预览页不会读取你的对话或 Run 数据</span>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

const Index = () => {
  const { user, csrfToken, logout, loading: authLoading } = useAuth();
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [initialMessages, setInitialMessages] = useState<StoredMessage[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [messagesLoading, setMessagesLoading] = useState(Boolean(conversationId));
  const [earlierCursor, setEarlierCursor] = useState<number | null>(null);
  const [earlierLoading, setEarlierLoading] = useState(false);
  const [loadedConversationId, setLoadedConversationId] = useState<string | null>(null);
  const [draftKey, setDraftKey] = useState(0);

  const refreshConversations = useCallback(async (query = searchQuery) => {
    if (!user) return;
    try {
      const response = await listConversations(query);
      setConversations(response.items);
    } catch (error) {
      toast.error((error as Error).message || "无法加载会话列表");
    } finally {
      setListLoading(false);
    }
  }, [searchQuery, user]);

  useEffect(() => {
    if (!user) {
      setListLoading(false);
      return;
    }
    setListLoading(true);
    const timer = window.setTimeout(() => {
      void refreshConversations(searchQuery);
    }, searchQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [refreshConversations, searchQuery, user]);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;
    if (!user || !conversationId) {
      setActiveConversation(null);
      setInitialMessages([]);
      setEarlierCursor(null);
      setLoadedConversationId(null);
      setMessagesLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setMessagesLoading(true);
    setLoadedConversationId(null);
    const refreshStreamingMessages = async (attempt: number) => {
      if (cancelled || attempt > 6) return;
      try {
        const response = await listMessages(conversationId);
        if (cancelled) return;
        setInitialMessages(response.items);
        setEarlierCursor(response.next_before ?? null);
        if (response.items.some((message) => message.status === "streaming")) {
          retryTimer = window.setTimeout(
            () => void refreshStreamingMessages(attempt + 1),
            Math.min(400 * (attempt + 1), 1600),
          );
        }
      } catch {
        // The initial load already surfaced errors. Polling is best-effort.
      }
    };

    void Promise.all([
      getConversation(conversationId),
      listMessages(conversationId),
    ]).then(([conversation, messageResponse]) => {
      if (cancelled) return;
      setActiveConversation(conversation);
      setInitialMessages(messageResponse.items);
      setEarlierCursor(messageResponse.next_before ?? null);
      setLoadedConversationId(conversationId);
      if (messageResponse.items.some((message) => message.status === "streaming")) {
        retryTimer = window.setTimeout(
          () => void refreshStreamingMessages(1),
          400,
        );
      }
    }).catch((error) => {
      if (cancelled) return;
      setLoadedConversationId(null);
      toast.error((error as Error).message || "无法加载这个会话");
      navigate("/", { replace: true });
    }).finally(() => {
      if (!cancelled) setMessagesLoading(false);
    });

    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [conversationId, navigate, user]);

  const handleLoadEarlier = useCallback(async () => {
    if (!conversationId || earlierCursor === null || earlierLoading) return;
    setEarlierLoading(true);
    try {
      const response = await listMessages(conversationId, 50, earlierCursor);
      setInitialMessages((current) => {
        const known = new Set(current.map((message) => message.id));
        return [
          ...response.items.filter((message) => !known.has(message.id)),
          ...current,
        ];
      });
      setEarlierCursor(response.next_before ?? null);
    } catch (error) {
      toast.error((error as Error).message || "无法加载更早消息");
    } finally {
      setEarlierLoading(false);
    }
  }, [conversationId, earlierCursor, earlierLoading]);

  const handleNewChat = useCallback(() => {
    setActiveConversation(null);
    setInitialMessages([]);
    setEarlierCursor(null);
    setLoadedConversationId(null);
    setMessagesLoading(false);
    setDraftKey((current) => current + 1);
    navigate("/");
  }, [navigate]);

  const handleConversationCreated = useCallback((conversation: Conversation) => {
    setConversations((current) => [
      conversation,
      ...current.filter((item) => item.id !== conversation.id),
    ]);
    navigate(`/chat/${conversation.id}`, { replace: true });
  }, [navigate]);

  const handleRename = useCallback(async (conversation: Conversation) => {
    const title = window.prompt("为这段对话输入新标题", conversation.title)?.trim();
    if (!title || title === conversation.title) return;
    try {
      const updated = await renameConversation(conversation.id, title, csrfToken);
      setConversations((current) =>
        current.map((item) => item.id === updated.id ? { ...item, ...updated } : item),
      );
      if (activeConversation?.id === updated.id) {
        setActiveConversation(updated);
      }
    } catch (error) {
      toast.error((error as Error).message || "重命名失败");
    }
  }, [activeConversation?.id, csrfToken]);

  const handleDelete = useCallback(async (conversation: Conversation) => {
    if (!window.confirm(`确定删除“${conversation.title}”吗？`)) return;
    try {
      await deleteConversation(conversation.id, csrfToken);
      setConversations((current) =>
        current.filter((item) => item.id !== conversation.id),
      );
      if (conversation.id === conversationId) {
        handleNewChat();
      }
      toast.success("会话已删除");
    } catch (error) {
      toast.error((error as Error).message || "删除失败");
    }
  }, [conversationId, csrfToken, handleNewChat]);

  if (authLoading) {
    return (
      <main className="grid min-h-dvh place-items-center bg-background text-muted-foreground">
        <div className="flex items-center gap-2 text-xs">
          <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          正在准备工作区
        </div>
      </main>
    );
  }

  if (!user) return <WorkspacePreview />;

  const displayedConversation = conversationId &&
    activeConversation?.id === conversationId
    ? activeConversation
    : null;
  const isConversationLoading = Boolean(conversationId) &&
    (messagesLoading || loadedConversationId !== conversationId);

  return (
    <SidebarProvider>
      <div className="flex h-dvh w-full overflow-hidden bg-background">
        <a href="#workspace-main" className="skip-link">跳到主要内容</a>
        <ChatSidebar
          onNewChat={handleNewChat}
          conversations={conversations}
          activeConversationId={conversationId}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onSelect={(conversation) => navigate(`/chat/${conversation.id}`)}
          onRename={(conversation) => void handleRename(conversation)}
          onDelete={(conversation) => void handleDelete(conversation)}
          loading={listLoading}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="z-20 flex min-h-[4.5rem] shrink-0 items-center border-b border-border bg-background px-4 sm:px-6">
            <div className="flex w-full items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <SidebarTrigger className="h-9 w-9 rounded-xl border border-border/70 bg-background/80 text-muted-foreground hover:bg-muted" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h1 className="truncate text-sm font-semibold sm:text-base">
                      {displayedConversation?.title || "新的对话"}
                    </h1>
                  </div>
                  <p className="mt-0.5 hidden truncate text-xs text-muted-foreground sm:block">
                    与启点一起梳理问题、研究信息和执行任务
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden items-center gap-2 rounded-full border border-border/70 bg-background/70 py-1.5 pl-2 pr-3 shadow-sm sm:flex">
                  <div className="grid h-7 w-7 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                    {user.display_name?.trim().slice(0, 1) || "启"}
                  </div>
                  <div className="max-w-36 text-left">
                    <p className="truncate text-xs font-medium">{user?.display_name}</p>
                    <p className="truncate text-[10px] text-muted-foreground">{user?.email}</p>
                  </div>
                </div>
                <WorkspaceThemeToggle />
                <button
                  type="button"
                  onClick={() => void logout()}
                  className="grid h-11 w-11 place-items-center rounded-xl border border-border bg-background text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="退出登录"
                  title="退出登录"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
          </header>

          <main id="workspace-main" className="relative w-full flex-1 overflow-hidden">
            {isConversationLoading ? (
              <div className="relative z-10 flex h-full items-center justify-center text-muted-foreground">
                <LoaderCircle className="h-5 w-5 animate-spin" />
                <span className="ml-2 text-xs">正在恢复会话</span>
              </div>
            ) : (
              <ChatContainer
                key={conversationId || `new-conversation-${draftKey}`}
                conversationId={conversationId}
                initialMessages={
                  conversationId && loadedConversationId === conversationId
                    ? initialMessages
                    : []
                }
                onConversationCreated={handleConversationCreated}
                onConversationChanged={() => void refreshConversations()}
                hasEarlierMessages={earlierCursor !== null}
                loadingEarlierMessages={earlierLoading}
                onLoadEarlierMessages={() => void handleLoadEarlier()}
              />
            )}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
};

export default Index;
