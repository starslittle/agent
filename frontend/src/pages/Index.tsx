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
import { LoaderCircle, LogOut } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

const Index = () => {
  const { user, csrfToken, logout } = useAuth();
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
    try {
      const response = await listConversations(query);
      setConversations(response.items);
    } catch (error) {
      toast.error((error as Error).message || "无法加载会话列表");
    } finally {
      setListLoading(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    setListLoading(true);
    const timer = window.setTimeout(() => {
      void refreshConversations(searchQuery);
    }, searchQuery ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [refreshConversations, searchQuery]);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;
    if (!conversationId) {
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
  }, [conversationId, navigate]);

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

  const displayedConversation = conversationId &&
    activeConversation?.id === conversationId
    ? activeConversation
    : null;
  const isConversationLoading = Boolean(conversationId) &&
    (messagesLoading || loadedConversationId !== conversationId);

  return (
    <SidebarProvider>
      <div className="flex h-screen w-full overflow-hidden bg-[#f5f7fb] dark:bg-[#080a13]">
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
          <header className="z-20 flex h-[4.5rem] flex-shrink-0 items-center border-b border-border/60 bg-background/75 px-4 backdrop-blur-xl sm:px-6">
            <div className="flex w-full items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <SidebarTrigger className="h-9 w-9 rounded-xl border border-border/70 bg-background/80 text-muted-foreground hover:bg-muted" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h1 className="truncate text-sm font-semibold sm:text-base">
                      {displayedConversation?.title || "新的对话"}
                    </h1>
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
