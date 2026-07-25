import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import { postQueryStreamGraph } from "@/lib/api";
import { useAuth } from "@/auth/AuthProvider";
import { ArrowDown, ArrowUpRight } from "lucide-react";

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  thinking?: boolean;
  thinkingFinished?: boolean;
}

function uid() {
  return Math.random().toString(36).slice(2);
}

export const ChatContainer: React.FC = () => {
  const { csrfToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isFollowingLatest, setIsFollowingLatest] = useState(true);

  const listRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const isFollowingLatestRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  
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
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsGenerating(false);
    }
  }, []);

  const handleSend = useCallback(async (text: string, deep: boolean) => {
    scrollToLatest();

    const userMsg: Message = { id: uid(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    const assistantId = uid();
    // 初始状态：thinking 为 true，content 为空
    setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "", thinking: true, thinkingFinished: false }]);

    // 如果有之前的请求，取消它
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsGenerating(true);

    try {
      const agentName = deep ? "research_agent" : undefined;
      
      const chatHistory = messages
        .filter(m => !m.thinking)
        .map(m => ({ role: m.role, content: m.content }));
      
      const payload = { 
        query: text, 
        agent_name: agentName,
        chat_history: chatHistory.length > 0 ? chatHistory : null
      };

      // 使用局部变量累积文本，直接更新 Messages
      let accumulatedContent = "";
      
      await postQueryStreamGraph(
        payload,
        (delta: string, isThinking?: boolean, thinkingFinished?: boolean) => {
          accumulatedContent += delta;

          // 在回调中直接更新主状态
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id === assistantId) {
                return {
                  ...m,
                  content: accumulatedContent,
                  thinking: isThinking ?? m.thinking,
                  thinkingFinished: thinkingFinished ?? m.thinkingFinished,
                };
              }
              return m;
            })
          );
        },
        csrfToken,
        controller.signal
      );
      
      if (!accumulatedContent) {
        throw new Error("流式输出未收到任何内容");
      }

    } catch (err: unknown) {
      // 如果是用户手动停止，不做错误处理，只确保 thinking 结束
      if ((err as Error).name === "AbortError") {
        setMessages((prev) => prev.map((m) =>
          m.id === assistantId ? { ...m, thinking: false } : m
        ));
        return;
      }

      console.error("对话失败:", err);
      setMessages((prev) => prev.map((m) => 
        m.id === assistantId 
          ? { 
              ...m, 
              content: `请求失败：${(err as Error)?.message || String(err)}`, 
              thinking: false 
            }
          : m
      ));
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  }, [csrfToken, messages, scrollToLatest]);

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
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`${message.role === "user" ? "flex justify-end" : "flex justify-start"} animate-in fade-in-0 slide-in-from-bottom-2 duration-300 motion-reduce:animate-none motion-reduce:transition-none`}
                >
                  <ChatMessage
                    role={message.role}
                    content={message.content}
                    thinking={message.thinking}
                    thinkingFinished={message.thinkingFinished}
                  />
                </div>
              ))
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
          <ChatInput onSend={handleSend} loading={isGenerating} onStop={handleStop} />
          <p className="mt-2.5 text-center text-[10px] text-muted-foreground">
            奇点AI可能会犯错，请核对重要信息。
          </p>
        </div>
      </footer>
    </section>
  );
};

export default ChatContainer;
