
import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import { Button } from "@/components/ui/button";
import { postQuery } from "@/lib/api";

interface Message {
  id: string;
  role: ChatRole;
  content: string;
  thinking?: boolean;
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

  const streamRef = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const clearStream = () => {
    if (streamRef.current) {
      window.clearInterval(streamRef.current);
      streamRef.current = null;
    }
  };

  useEffect(() => () => clearStream(), []);

  // 消息变更时滚动到底部，保持对话区在框内滚动
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const handleSend = useCallback(async (text: string, deep: boolean) => {
    clearStream();
    const userMsg: Message = { id: uid(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    const thinkingId = uid();
    setMessages((prev) => [...prev, { id: thinkingId, role: "assistant", content: "", thinking: true }]);

    try {
      // 真实调用后端 API；深度思考 → 使用 research_agent，否则使用默认 agent
      const res = await postQuery({ query: text, agent_name: deep ? "research_agent" : undefined });
      const answer = res.answer || res.output || "";
      setMessages((prev) => prev.filter((m) => m.id !== thinkingId).concat({
        id: uid(),
        role: "assistant",
        content: answer,
      }));
    } catch (err: any) {
      setMessages((prev) => prev.filter((m) => m.id !== thinkingId).concat({
        id: uid(),
        role: "assistant",
        content: `请求失败：${err?.message || String(err)}`,
      }));
    }
  }, []);

  return (
    <section className="w-full max-w-3xl mx-auto">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-tr from-primary to-accent bg-clip-text text-transparent">奇点AI · 智能体对话</h1>
        <div className="hidden sm:flex gap-2">
          <Button variant="default" className="animate-glow">全局设置</Button>
        </div>
      </header>

      <main className="mb-8">
        {/* 对话区限制在固定高度的可滚动容器内 */}
        <div ref={listRef} className="h-[60vh] overflow-y-auto flex flex-col gap-6 pr-2">
          {messages.map((m) => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <ChatMessage role={m.role} content={m.content} thinking={m.thinking} />
            </div>
          ))}
        </div>
      </main>

      <footer className="sticky bottom-4">
        <ChatInput onSend={handleSend} />
        <p className="mt-3 text-xs text-gray-500 text-center">思考过程仅作内部推理提示，不展示隐私性内容。</p>
      </footer>
    </section>
  );
};

export default ChatContainer;
