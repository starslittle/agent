
import React, { useCallback, useEffect, useRef, useState } from "react";
import ChatMessage, { ChatRole } from "./ChatMessage";
import ChatInput from "./ChatInput";
import { Button } from "@/components/ui/button";

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

  const clearStream = () => {
    if (streamRef.current) {
      window.clearInterval(streamRef.current);
      streamRef.current = null;
    }
  };

  useEffect(() => () => clearStream(), []);

  const mockGenerate = useCallback((prompt: string, deep: boolean) => {
    const base = `这是对你问题的回应：${prompt}\n\n- 我将以条列方式给出要点\n- 支持 Markdown，如 **加粗**、代码块等\n\n感谢使用「奇点AI」！`;
    const deepPrefix = deep ? "(深度思考已启用) " : "";
    return deepPrefix + base;
  }, []);

  const handleSend = useCallback((text: string, deep: boolean) => {
    clearStream();
    const userMsg: Message = { id: uid(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);

    const thinkingId = uid();
    setMessages((prev) => [...prev, { id: thinkingId, role: "assistant", content: "", thinking: true }]);

    const startStream = () => {
      setMessages((prev) => prev.filter((m) => m.id !== thinkingId).concat({
        id: uid(),
        role: "assistant",
        content: "",
      }));

      const full = mockGenerate(text, deep);
      const tokens = full.split(/(\s+)/);

      streamRef.current = window.setInterval(() => {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (!last || last.role !== "assistant") return prev;

          const nextToken = tokens.shift();
          if (nextToken === undefined) {
            clearStream();
            return prev;
          }
          const updated = { ...last, content: (last.content || "") + nextToken };
          return [...prev.slice(0, -1), updated];
        });

        if (tokens.length === 0) {
          clearStream();
        }
      }, 35);
    };

    if (deep) {
      setTimeout(startStream, 900);
    } else {
      setTimeout(startStream, 200);
    }
  }, [mockGenerate]);

  return (
    <section className="w-full max-w-3xl mx-auto">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-tr from-primary to-accent bg-clip-text text-transparent">奇点AI · 智能体对话</h1>
        <div className="hidden sm:flex gap-2">
          <Button variant="glow" className="animate-glow">全局设置</Button>
        </div>
      </header>

      <main className="min-h-[50vh] flex flex-col gap-6 mb-8">
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <ChatMessage role={m.role} content={m.content} thinking={m.thinking} />
          </div>
        ))}
      </main>

      <footer className="sticky bottom-4">
        <ChatInput onSend={handleSend} />
        <p className="mt-3 text-xs text-gray-500 text-center">思考过程仅作内部推理提示，不展示隐私性内容。</p>
      </footer>
    </section>
  );
};

export default ChatContainer;
