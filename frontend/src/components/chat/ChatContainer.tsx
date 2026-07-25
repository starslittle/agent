import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import { postQueryStreamGraph } from "@/lib/api";

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
  const [messages, setMessages] = useState<Message[]>([{
    id: uid(),
    role: "assistant",
    content: "你好，我是奇点AI。告诉我你想聊什么吧！",
  }]);

  const listRef = useRef<HTMLDivElement | null>(null);
  
  // 移除：streamRef, streamingMessageId, streamingContent 相关的状态和 Effect
  // 这些中间状态是导致卡顿和逻辑复杂的元凶

  // 消息自动滚动
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    // 使用 requestAnimationFrame 确保在渲染完成后滚动，体验更顺滑
    requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
    });
  }, [messages]);

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
  }, [messages]);

  return (
    <section className="flex flex-col h-full w-full relative">
      {/* 消息区与输入区共用同一个滚动容器，滚动条可延伸到底部 */}
      <main className="flex-1 overflow-y-auto min-h-0 scroll-smooth" ref={listRef}>
        <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 min-h-full flex flex-col">
          <div className="flex flex-col gap-6 py-6 pb-6">
            {messages.map((m) => (
              <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <ChatMessage role={m.role} content={m.content} thinking={m.thinking} thinkingFinished={m.thinkingFinished} />
              </div>
            ))}
          </div>
          {/* 输入框区域：在滚动容器内吸底，确保滚动条轨道到最底部 */}
          <footer className="sticky bottom-0 mt-auto py-4 bg-background border-t border-border/60 z-10">
          <ChatInput onSend={handleSend} loading={isGenerating} onStop={handleStop} />
          <p className="mt-3 text-xs text-gray-500 text-center">思考过程仅作内部推理提示，不展示隐私性内容。</p>
          </footer>
        </div>
      </main>
    </section>
  );
};

export default ChatContainer;
