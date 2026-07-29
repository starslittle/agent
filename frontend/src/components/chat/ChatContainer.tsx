import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import {
  cancelAgentRun,
  createConversation,
  postConversationStream,
  type Conversation,
  type StoredMessage,
} from "@/lib/chat-api";
import { useAuth } from "@/auth/AuthProvider";
import { ArrowDown, ArrowUpRight, LoaderCircle } from "lucide-react";
import { toast } from "sonner";

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  status?: StoredMessage["status"];
  thinking?: boolean;
  thinkingFinished?: boolean;
}

function uid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    const value = character === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

interface ChatContainerProps {
  conversationId?: string | null;
  initialMessages?: StoredMessage[];
  onConversationCreated?: (conversation: Conversation) => void;
  onConversationChanged?: () => void;
  hasEarlierMessages?: boolean;
  loadingEarlierMessages?: boolean;
  onLoadEarlierMessages?: () => void;
}

function toViewMessage(message: StoredMessage): Message {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    status: message.status,
    thinking: message.status === "streaming",
    thinkingFinished: message.status !== "streaming",
  };
}

export const ChatContainer: React.FC<ChatContainerProps> = ({
  conversationId,
  initialMessages = [],
  onConversationCreated,
  onConversationChanged,
  hasEarlierMessages = false,
  loadingEarlierMessages = false,
  onLoadEarlierMessages,
}) => {
  const { csrfToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>(
    () => initialMessages.map(toViewMessage),
  );
  const [isFollowingLatest, setIsFollowingLatest] = useState(true);

  const listRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const isFollowingLatestRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRunRef = useRef<{
    id: string;
    protocolVersion: number;
  } | null>(null);
  const stopRequestedRef = useRef(false);
  const cancellationInFlightRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    setMessages((current) => {
      const incomingByID = new Map(
        initialMessages.map((message) => [message.id, message]),
      );
      const merged = current.map((message) => {
        const incoming = incomingByID.get(message.id);
        if (!incoming) return message;
        if (message.status === "streaming" && incoming.status === "streaming") {
          return message;
        }
        return toViewMessage(incoming);
      });
      const known = new Set(merged.map((message) => message.id));
      const earlier = initialMessages
        .filter((message) => !known.has(message.id))
        .map(toViewMessage);
      return earlier.length > 0 ? [...earlier, ...merged] : merged;
    });
  }, [initialMessages]);
  
  // 移除：streamRef, streamingMessageId, streamingContent 相关的状态和 Effect
  // 这些中间状态是导致卡顿和逻辑复杂的元凶

  const setFollowingLatest = useCallback((following: boolean) => {
    isFollowingLatestRef.current = following;
    setIsFollowingLatest(following);
  }, []);

  const scrollToLatest = useCallback((behavior: ScrollBehavior = "auto") => {
    const el = listRef.current;
    if (!el) return;

    setFollowingLatest(true);
    requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior });
      lastScrollTopRef.current = el.scrollTop;
    });
  }, [setFollowingLatest]);

  // 仅当用户仍在阅读最新内容时跟随流式回复。
  useEffect(() => {
    if (isFollowingLatestRef.current) {
      scrollToLatest();
    }
  }, [messages, scrollToLatest]);

  // 平滑打字、Markdown 和图片加载也可能改变消息高度。
  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      if (isFollowingLatestRef.current) {
        scrollToLatest();
      }
    });

    observer.observe(content);
    return () => observer.disconnect();
  }, [scrollToLatest]);

  const handleScroll = useCallback(() => {
    const el = listRef.current;
    if (!el) return;

    const currentScrollTop = el.scrollTop;
    const distanceToBottom = el.scrollHeight - currentScrollTop - el.clientHeight;
    const isNearBottom = distanceToBottom <= 80;
    const isScrollingUp = currentScrollTop < lastScrollTopRef.current - 2;

    if (isNearBottom) {
      setFollowingLatest(true);
    } else if (isScrollingUp) {
      setFollowingLatest(false);
    }

    lastScrollTopRef.current = currentScrollTop;
  }, [setFollowingLatest]);

  const [isGenerating, setIsGenerating] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  const requestRunCancellation = useCallback(async (
    activeRun: { id: string; protocolVersion: number },
  ) => {
    if (cancellationInFlightRef.current) return;

    cancellationInFlightRef.current = true;
    try {
      await cancelAgentRun(activeRun.id, csrfToken);
      // Keep consuming the stream until Go emits its authoritative terminal
      // event. Aborting here can make the UI say "stopped" while the Run is
      // still active in PostgreSQL.
    } catch (error) {
      console.error("取消生成失败:", error);
      stopRequestedRef.current = false;
      if (mountedRef.current) {
        setIsCancelling(false);
        toast.error("取消失败，任务仍在运行，可再次点击停止");
      }
    } finally {
      cancellationInFlightRef.current = false;
    }
  }, [csrfToken]);

  const handleStop = useCallback(() => {
    if (!abortControllerRef.current || cancellationInFlightRef.current) return;
    stopRequestedRef.current = true;
    setIsCancelling(true);
    const activeRun = activeRunRef.current;
    if (activeRun) {
      void requestRunCancellation(activeRun);
    }
  }, [requestRunCancellation]);

  const handleSend = useCallback(async (text: string, deep: boolean) => {
    scrollToLatest();

    const clientMessageID = uid();
    const userMsg: Message = {
      id: clientMessageID,
      role: "user",
      content: text,
      status: "completed",
    };
    setMessages((prev) => [...prev, userMsg]);

    const assistantId = uid();
    // 初始状态：thinking 为 true，content 为空
    setMessages((prev) => [...prev, {
      id: assistantId,
      role: "assistant",
      content: "",
      status: "streaming",
      thinking: true,
      thinkingFinished: false,
    }]);

    // 如果有之前的请求，取消它
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsGenerating(true);
    let createdConversation: Conversation | null = null;
    let accumulatedContent = "";
    let terminalStatus: string | undefined;
    activeRunRef.current = null;
    stopRequestedRef.current = false;

    try {
      const agentName = deep ? "research_agent" : undefined;
      let targetConversationID = conversationId || "";
      if (!targetConversationID) {
        createdConversation = await createConversation(csrfToken, agentName);
        targetConversationID = createdConversation.id;
      }

      // 使用局部变量累积文本，直接更新 Messages
      await postConversationStream(
        targetConversationID,
        {
          content: text,
          client_message_id: clientMessageID,
          agent_name: agentName,
        },
        csrfToken,
        (event) => {
          if (event.type === "meta") {
            activeRunRef.current = {
              id: event.run_id,
              protocolVersion: event.protocol_version ?? 0,
            };
            if (stopRequestedRef.current) {
              void requestRunCancellation(activeRunRef.current);
            }
            setMessages((prev) => prev.map((message) => {
              if (message.id === clientMessageID) {
                return { ...message, id: event.user_message_id };
              }
              if (message.id === assistantId) {
                return { ...message, id: event.assistant_message_id };
              }
              return message;
            }));
            return;
          }
          if (event.type === "done") {
            terminalStatus = event.status;
            return;
          }
          if (event.type !== "delta" || !event.data) return;
          accumulatedContent += event.data;
          setMessages((prev) =>
            prev.map((message) => {
              if (message.id === assistantId ||
                  (event.type === "delta" && message.status === "streaming" && message.role === "assistant")) {
                return {
                  ...message,
                  content: accumulatedContent,
                  status: "streaming",
                  thinking: event.isThinking ?? message.thinking,
                  thinkingFinished: event.thinkingFinished ?? message.thinkingFinished,
                };
              }
              return message;
            }),
          );
        },
        controller.signal
      );

      if (terminalStatus === "stopped" || terminalStatus === "cancelled") {
        setMessages((prev) => prev.map((message) =>
          message.role === "assistant" && message.status === "streaming"
            ? {
                ...message,
                status: "stopped",
                thinking: false,
                thinkingFinished: true,
              }
            : message,
        ));
        return;
      }
      
      if (!accumulatedContent) {
        throw new Error("流式输出未收到任何内容");
      }
      setMessages((prev) => prev.map((message) =>
        message.role === "assistant" && message.status === "streaming"
          ? {
              ...message,
              status: "completed",
              thinking: false,
              thinkingFinished: true,
            }
          : message,
      ));
    } catch (err: unknown) {
      // Abort only represents a local stream teardown (for example component
      // unmount). A successful cancellation is reported by the server's done
      // event and must not be inferred from AbortError.
      if ((err as Error).name === "AbortError") {
        return;
      }

      console.error("对话失败:", err);
      setMessages((prev) => prev.map((m) => 
        m.role === "assistant" && m.status === "streaming"
          ? { 
              ...m, 
              content: accumulatedContent ||
                `请求失败：${(err as Error)?.message || String(err)}`,
              status: "failed",
              thinking: false 
            }
          : m
      ));
    } finally {
      abortControllerRef.current = null;
      activeRunRef.current = null;
      stopRequestedRef.current = false;
      if (mountedRef.current) {
        setIsGenerating(false);
        setIsCancelling(false);
        if (createdConversation) {
          onConversationCreated?.(createdConversation);
        }
        onConversationChanged?.();
      }
    }
  }, [
    conversationId,
    csrfToken,
    onConversationChanged,
    onConversationCreated,
    requestRunCancellation,
    scrollToLatest,
  ]);

  const suggestions = [
    {
      label: "梳理一个复杂问题",
      prompt: "帮我把一个复杂问题拆解成清晰、可执行的步骤",
    },
    {
      label: "研究一个新方向",
      prompt: "我想研究一个新方向，请帮我搭建分析框架",
    },
    {
      label: "完善手头的想法",
      prompt: "我有一个还不成熟的想法，请通过提问帮我完善它",
    },
  ];

  return (
    <section className="relative flex h-full w-full flex-col">
      <main
        className="min-h-0 flex-1 overflow-y-auto"
        ref={listRef}
        onScroll={handleScroll}
      >
        <div
          ref={contentRef}
          className="mx-auto flex min-h-full w-full max-w-4xl flex-col px-4 sm:px-6 lg:px-8"
        >
          <div className="flex flex-1 flex-col gap-7 pb-48 pt-8 sm:pt-10">
            {messages.length === 0 ? (
              <div className="flex min-h-[calc(100vh-17rem)] flex-1 flex-col items-center justify-center text-center">
                <div className="relative mb-7 h-20 w-20" aria-hidden="true">
                  <div className="absolute inset-[4px] rotate-[-18deg] rounded-[50%] border border-violet-400/35" />
                  <div className="absolute inset-[13px] rotate-[22deg] rounded-[50%] border border-blue-400/30" />
                  <div className="absolute inset-0 animate-[spin_20s_linear_infinite] rounded-[50%] border border-transparent border-t-violet-500/60 motion-reduce:animate-none" />
                  <div className="absolute left-1/2 top-1/2 grid h-11 w-11 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-[#121629] text-sm font-bold text-white shadow-[0_12px_32px_-12px_rgba(91,33,182,0.7)] dark:bg-white dark:text-[#121629]">
                    奇
                  </div>
                </div>

                <p className="mb-3 text-[11px] font-semibold tracking-[0.18em] text-primary">
                  奇点工作空间
                </p>
                <h2 className="text-3xl font-semibold tracking-[-0.045em] text-foreground sm:text-[2.6rem]">
                  今天想从哪里开始？
                </h2>
                <p className="mt-3 max-w-md text-sm leading-6 text-muted-foreground">
                  描述你的目标，或从一个方向开始。奇点AI会与你一起拆解、研究并推进。
                </p>

                <div className="mt-8 grid w-full max-w-2xl gap-3 sm:grid-cols-3">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion.label}
                      type="button"
                      onClick={() => void handleSend(suggestion.prompt, false)}
                      className="group flex min-h-24 flex-col justify-between rounded-2xl border border-white/80 bg-white/65 p-4 text-left shadow-[0_12px_40px_-28px_rgba(31,41,70,0.35)] backdrop-blur transition hover:-translate-y-1 hover:border-violet-300/60 hover:bg-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 motion-reduce:transform-none dark:border-white/[0.08] dark:bg-white/[0.035] dark:hover:border-violet-400/25 dark:hover:bg-white/[0.06]"
                    >
                      <span className="text-sm font-medium text-foreground">
                        {suggestion.label}
                      </span>
                      <span className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
                        开始对话
                        <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {hasEarlierMessages && (
                  <div className="flex justify-center pb-1">
                    <button
                      type="button"
                      onClick={onLoadEarlierMessages}
                      disabled={loadingEarlierMessages}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-background/75 px-3 py-1.5 text-[11px] text-muted-foreground transition hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-60"
                    >
                      {loadingEarlierMessages && <LoaderCircle className="h-3 w-3 animate-spin" />}
                      加载更早消息
                    </button>
                  </div>
                )}
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`${message.role === "user" ? "flex justify-end" : "flex justify-start"} animate-in fade-in-0 slide-in-from-bottom-2 duration-300 motion-reduce:animate-none motion-reduce:transition-none`}
                  >
                    <ChatMessage
                      role={message.role}
                      content={message.content}
                      status={message.status}
                      thinking={message.thinking}
                      thinkingFinished={message.thinkingFinished}
                    />
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </main>

      <footer className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[#f5f7fb] via-[#f5f7fb]/95 to-transparent px-4 pb-4 pt-12 dark:from-[#080a13] dark:via-[#080a13]/95 sm:px-6 sm:pb-5">
        {!isFollowingLatest && messages.length > 0 && (
          <button
            type="button"
            onClick={() => scrollToLatest("smooth")}
            className="pointer-events-auto absolute left-1/2 top-1 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border/80 bg-background/95 px-3.5 py-2 text-xs font-medium text-foreground shadow-[0_10px_30px_-12px_rgba(31,41,70,0.45)] backdrop-blur transition hover:-translate-y-0.5 hover:bg-background focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 motion-reduce:transform-none"
            aria-label="回到最新消息"
          >
            <ArrowDown className="h-3.5 w-3.5" />
            回到最新
          </button>
        )}
        <div className="pointer-events-auto mx-auto w-full max-w-4xl">
          <ChatInput
            onSend={handleSend}
            loading={isGenerating}
            stopping={isCancelling}
            onStop={handleStop}
          />
          <p className="mt-2.5 text-center text-[10px] text-muted-foreground">
            奇点AI可能会犯错，请核对重要信息。
          </p>
        </div>
      </footer>
    </section>
  );
};

export default ChatContainer;
