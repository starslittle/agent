import React, { useCallback, useEffect, useState } from "react";
import ChatContainer from "@/components/chat/ChatContainer";
import { WorkspaceLoadingScreen, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { useWorkspaceConversations } from "@/components/workspace/workspace-conversations-context";
import { useAuth } from "@/auth/AuthProvider";
import {
  getConversation,
  listMessages,
  type Conversation,
  type StoredMessage,
} from "@/lib/chat-api";
import { LoaderCircle, MessageSquare, Sparkles } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { QidianMark } from "@/brand/QidianMark";

function WorkspacePreview() {
  return (
    <WorkspaceShell
      title="工作区预览"
      subtitle="一个助手，多种专业 Skill"
      mainId="preview-main"
      mainClassName="flex items-center justify-center overflow-y-auto px-5 py-12 sm:px-8"
    >
      <section className="w-full max-w-3xl">
            <QidianMark className="h-16 w-16" />
            <p className="mt-6 text-xs font-semibold tracking-[0.16em] text-primary">启点工作空间</p>
            <h2 className="mt-3 max-w-2xl text-pretty text-3xl font-semibold tracking-[-0.04em] sm:text-5xl sm:leading-[1.12]">
              从一个问题开始，<br className="hidden sm:block" />把思考推进到下一步。
            </h2>
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
                  <h3 className="mt-5 text-sm font-semibold">{title}</h3>
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
    </WorkspaceShell>
  );
}

const Index = () => {
  const { user, loading: authLoading } = useAuth();
  const { conversationId } = useParams<{ conversationId?: string }>();
  const navigate = useNavigate();
  const {
    conversations,
    newChatVersion,
    refreshConversations,
    upsertConversation,
  } = useWorkspaceConversations();
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [initialMessages, setInitialMessages] = useState<StoredMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(Boolean(conversationId));
  const [earlierCursor, setEarlierCursor] = useState<number | null>(null);
  const [earlierLoading, setEarlierLoading] = useState(false);
  const [loadedConversationId, setLoadedConversationId] = useState<string | null>(null);

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

  const handleConversationCreated = useCallback((conversation: Conversation) => {
    upsertConversation(conversation);
    navigate(`/chat/${conversation.id}`, { replace: true });
  }, [navigate, upsertConversation]);

  if (authLoading) {
    return <WorkspaceLoadingScreen />;
  }

  if (!user) return <WorkspacePreview />;

  const displayedConversation = conversationId
    ? conversations.find((conversation) => conversation.id === conversationId) ??
      (activeConversation?.id === conversationId ? activeConversation : null)
    : null;
  const isConversationLoading = Boolean(conversationId) &&
    (messagesLoading || loadedConversationId !== conversationId);

  return (
    <WorkspaceShell
      title={displayedConversation?.title || "新的对话"}
      subtitle="与启点一起梳理问题、研究信息和执行任务"
      mainId="workspace-main"
    >
      {isConversationLoading ? (
        <div className="relative z-10 flex h-full items-center justify-center text-muted-foreground">
          <LoaderCircle className="h-5 w-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          <span className="ml-2 text-xs">正在恢复会话…</span>
        </div>
      ) : (
        <ChatContainer
          key={conversationId || `new-conversation-${newChatVersion}`}
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
    </WorkspaceShell>
  );
};

export default Index;
