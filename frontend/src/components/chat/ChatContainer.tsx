import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import {
  attachAgentRun,
  cancelAgentRun,
  createAgentRun,
  createConversation,
  listAgentRuns,
  type Conversation,
  type ConversationStreamEvent,
  type RuntimeActivity,
  type RuntimeArtifact,
  type StoredMessage,
} from "@/lib/chat-api";
import {
  conversationStreamReducer,
  createConversationStreamState,
} from "@/lib/conversation-stream-reducer";
import {
  canCancelRun,
  idleRunLifecycle,
  isRunBusy,
  runLifecycleReducer,
  type RunLifecycleAction,
  type RunLifecycleState,
} from "@/lib/run-lifecycle";
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
  activities?: RuntimeActivity[];
  artifacts?: RuntimeArtifact[];
}

function uid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
    /[xy]/g,
    (character) => {
      const random = Math.floor(Math.random() * 16);
      const value = character === "x" ? random : (random & 0x3) | 0x8;
      return value.toString(16);
    },
  );
}

function waitForRetry(delay: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(
      new DOMException("The operation was aborted", "AbortError"),
    );
  }
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("The operation was aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, delay);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function terminalMessageStatus(status?: string): StoredMessage["status"] {
  if (status === "cancelled" || status === "stopped") return "stopped";
  if (status === "failed" || status === "timed_out") return "failed";
  return "completed";
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
  const [messages, setMessages] = useState<Message[]>(() =>
    initialMessages.map(toViewMessage),
  );
  const [isFollowingLatest, setIsFollowingLatest] = useState(true);

  const listRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const isFollowingLatestRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const [runState, setRunState] = useState<RunLifecycleState>(idleRunLifecycle);
  const runStateRef = useRef<RunLifecycleState>(runState);

  const transitionRun = useCallback((action: RunLifecycleAction) => {
    const next = runLifecycleReducer(runStateRef.current, action);
    runStateRef.current = next;
    if (mountedRef.current) setRunState(next);
    return next;
  }, []);

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

  const scrollToLatest = useCallback(
    (behavior: ScrollBehavior = "auto") => {
      const el = listRef.current;
      if (!el) return;

      setFollowingLatest(true);
      requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight, behavior });
        lastScrollTopRef.current = el.scrollTop;
      });
    },
    [setFollowingLatest],
  );

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
    const distanceToBottom =
      el.scrollHeight - currentScrollTop - el.clientHeight;
    const isNearBottom = distanceToBottom <= 80;
    const isScrollingUp = currentScrollTop < lastScrollTopRef.current - 2;

    if (isNearBottom) {
      setFollowingLatest(true);
    } else if (isScrollingUp) {
      setFollowingLatest(false);
    }

    lastScrollTopRef.current = currentScrollTop;
  }, [setFollowingLatest]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

  const requestRunCancellation = useCallback(
    async (runID: string) => {
      transitionRun({ type: "cancel_requested", runID });
      try {
        await cancelAgentRun(runID, csrfToken);
        // Keep consuming the stream until Go emits its authoritative terminal
        // event. Aborting here can make the UI say "stopped" while the Run is
        // still active in PostgreSQL.
      } catch (error) {
        console.error("取消生成失败:", error);
        transitionRun({ type: "cancel_failed", runID });
        if (mountedRef.current) {
          toast.error("取消失败，任务仍在运行，可再次点击停止");
        }
      }
    },
    [csrfToken, transitionRun],
  );

  const handleStop = useCallback(() => {
    const activeRun = runStateRef.current;
    if (activeRun.phase !== "active") return;
    void requestRunCancellation(activeRun.runID);
  }, [requestRunCancellation]);

  const followRun = useCallback(
    async (
      runID: string,
      assistantMessageID: string,
      controller: AbortController,
    ) => {
      let streamState = {
        ...createConversationStreamState(),
        isStreaming: true,
      };
      let terminalReceived = false;
      let retryAttempt = 0;
      let reconnectNoticeShown = false;

      while (!controller.signal.aborted && !terminalReceived) {
        try {
          await attachAgentRun(
            runID,
            streamState.lastSequence,
            (event: ConversationStreamEvent) => {
              const sequence = "sequence" in event ? event.sequence : undefined;
              if (
                sequence !== undefined &&
                sequence <= streamState.lastSequence
              )
                return;

              streamState = conversationStreamReducer(streamState, event);
              transitionRun({
                type: "event_confirmed",
                runID,
                sequence,
              });

              if (event.type === "done") {
                terminalReceived = true;
                const status = terminalMessageStatus(event.status);
                setMessages((current) =>
                  current.map((message) =>
                    message.id === assistantMessageID
                      ? {
                          ...message,
                          content: streamState.answer || message.content,
                          activities: streamState.activities,
                          artifacts: streamState.artifacts,
                          status,
                          thinking: false,
                          thinkingFinished: true,
                        }
                      : message,
                  ),
                );
                transitionRun({ type: "done", runID });
                return;
              }

              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantMessageID
                    ? {
                        ...message,
                        content: streamState.answer,
                        activities: streamState.activities,
                        artifacts: streamState.artifacts,
                        status: "streaming",
                        thinking: true,
                        thinkingFinished: false,
                      }
                    : message,
                ),
              );
            },
            controller.signal,
          );
          retryAttempt = 0;
        } catch (error) {
          if ((error as Error).name === "AbortError") throw error;
          console.error("运行连接中断:", error);
          if (!reconnectNoticeShown && mountedRef.current) {
            reconnectNoticeShown = true;
            toast.error(
              (error as Error).message || "运行连接中断，正在重新连接",
            );
          }
        }

        if (!terminalReceived) {
          retryAttempt += 1;
          await waitForRetry(
            Math.min(250 * 2 ** (retryAttempt - 1), 2000),
            controller.signal,
          );
        }
      }

      if (terminalReceived) onConversationChanged?.();
    },
    [onConversationChanged, transitionRun],
  );

  const recoverableAssistantID = initialMessages.find(
    (message) => message.role === "assistant" && message.status === "streaming",
  )?.id;

  useEffect(() => {
    if (
      !conversationId ||
      !recoverableAssistantID ||
      runStateRef.current.phase !== "idle"
    )
      return;

    const controller = new AbortController();
    let disposed = false;
    void listAgentRuns()
      .then((response) => {
        if (disposed) return;
        const activeRun = response.items.find(
          (run) =>
            run.conversation_id === conversationId &&
            ["queued", "running", "cancel_requested"].includes(run.status),
        );
        if (!activeRun) return;

        abortControllerRef.current?.abort();
        abortControllerRef.current = controller;
        setMessages((current) =>
          current.map((message) =>
            message.id === recoverableAssistantID
              ? {
                  ...message,
                  content: "",
                  activities: [],
                  artifacts: [],
                  status: "streaming",
                  thinking: true,
                  thinkingFinished: false,
                }
              : message,
          ),
        );
        transitionRun({
          type: "run_available",
          runID: activeRun.id,
          assistantMessageID: recoverableAssistantID,
          protocolVersion: activeRun.protocol_version,
          status: activeRun.status,
        });
        return followRun(activeRun.id, recoverableAssistantID, controller);
      })
      .catch((error) => {
        if ((error as Error).name !== "AbortError" && !disposed) {
          console.error("恢复运行失败:", error);
          toast.error("暂时无法恢复运行，正在保留服务端状态");
        }
      })
      .finally(() => {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      });

    return () => {
      disposed = true;
      controller.abort();
    };
  }, [conversationId, followRun, recoverableAssistantID, transitionRun]);

  const handleSend = useCallback(
    async (text: string, deep: boolean) => {
      if (isRunBusy(runStateRef.current)) return;
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
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          status: "streaming",
          thinking: true,
          thinkingFinished: false,
        },
      ]);

      const controller = new AbortController();
      abortControllerRef.current = controller;
      transitionRun({ type: "create_started" });
      let createdConversation: Conversation | null = null;
      let conversationCreatedNotified = false;
      let runCreated = false;

      try {
        const agentName = deep ? "research_agent" : undefined;
        let targetConversationID = conversationId || "";
        if (!targetConversationID) {
          createdConversation = await createConversation(csrfToken, agentName);
          targetConversationID = createdConversation.id;
        }

        const run = await createAgentRun(
          targetConversationID,
          {
            content: text,
            client_message_id: clientMessageID,
            idempotency_key: clientMessageID,
            agent_name: agentName,
          },
          csrfToken,
        );
        runCreated = true;
        setMessages((current) =>
          current.map((message) => {
            if (message.id === clientMessageID) {
              return { ...message, id: run.user_message_id };
            }
            if (message.id === assistantId) {
              return { ...message, id: run.assistant_message_id };
            }
            return message;
          }),
        );
        transitionRun({
          type: "run_available",
          runID: run.run_id,
          assistantMessageID: run.assistant_message_id,
          protocolVersion: run.protocol_version,
          status: run.status,
        });
        if (createdConversation) {
          conversationCreatedNotified = true;
          onConversationCreated?.(createdConversation);
        }
        await followRun(run.run_id, run.assistant_message_id, controller);
      } catch (err: unknown) {
        // Abort only represents a local stream teardown (for example component
        // unmount). A successful cancellation is reported by the server's done
        // event and must not be inferred from AbortError.
        if ((err as Error).name === "AbortError") {
          return;
        }

        console.error("对话失败:", err);
        toast.error((err as Error)?.message || "生成失败，请重试");
        if (!runCreated) transitionRun({ type: "create_failed" });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.status === "streaming"
              ? {
                  ...m,
                  status: "failed",
                  thinking: false,
                  thinkingFinished: true,
                }
              : m,
          ),
        );
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
        if (mountedRef.current) {
          if (createdConversation && !conversationCreatedNotified) {
            onConversationCreated?.(createdConversation);
          }
        }
      }
    },
    [
      conversationId,
      csrfToken,
      onConversationCreated,
      followRun,
      scrollToLatest,
      transitionRun,
    ],
  );

  const isGenerating = isRunBusy(runState);
  const isCancelling = runState.phase === "cancelling";
  const canStop = canCancelRun(runState);

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
                      className="group flex min-h-24 flex-col justify-between rounded-2xl border border-white/80 bg-white/65 p-4 text-left shadow-[0_12px_40px_-28px_rgba(31,41,70,0.35)] backdrop-blur transition-[color,background-color,border-color,transform] hover:-translate-y-1 hover:border-violet-300/60 hover:bg-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 motion-reduce:transform-none dark:border-white/[0.08] dark:bg-white/[0.035] dark:hover:border-violet-400/25 dark:hover:bg-white/[0.06]"
                    >
                      <span className="text-sm font-medium text-foreground">
                        {suggestion.label}
                      </span>
                      <span className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
                        开始对话
                        <ArrowUpRight
                          className="h-3.5 w-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                          aria-hidden="true"
                        />
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
                      className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-border/70 bg-background/75 px-3 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground disabled:pointer-events-none disabled:opacity-60"
                    >
                      {loadingEarlierMessages && (
                        <LoaderCircle
                          className="h-3 w-3 animate-spin motion-reduce:animate-none"
                          aria-hidden="true"
                        />
                      )}
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
                      activities={message.activities}
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
            className="pointer-events-auto absolute left-1/2 top-1 inline-flex min-h-11 -translate-x-1/2 items-center gap-1.5 rounded-full border border-border/80 bg-background/95 px-3.5 py-2 text-xs font-medium text-foreground shadow-[0_10px_30px_-12px_rgba(31,41,70,0.45)] backdrop-blur transition-[color,background-color,transform] hover:-translate-y-0.5 hover:bg-background focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/15 motion-reduce:transform-none"
            aria-label="回到最新消息"
          >
            <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
            回到最新
          </button>
        )}
        <div className="pointer-events-auto mx-auto w-full max-w-4xl">
          <ChatInput
            onSend={handleSend}
            loading={isGenerating}
            stopping={isCancelling}
            canStop={canStop}
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
