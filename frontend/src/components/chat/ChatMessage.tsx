
import React from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot } from "lucide-react";

export type ChatRole = "user" | "assistant";

export interface ChatMessageProps {
  role: ChatRole;
  content: string;
  thinking?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, thinking }) => {
  const isUser = role === "user";
  return (
    <article className="w-full flex items-start gap-3">
      {/* 用户消息：头像在右侧；助手消息：头像在左侧 */}
      {!isUser && (
        <Avatar className="mt-1">
          <AvatarFallback className="bg-gradient-to-br from-primary to-accent text-white">
            <Bot size={20} />
          </AvatarFallback>
        </Avatar>
      )}

      <div
        className={
          isUser
            ? "rounded-2xl px-4 py-3 bg-gradient-to-r from-blue-500 to-purple-600 text-white max-w-[80%] ml-auto order-1"
            : "rounded-2xl px-4 py-3 bg-white border border-gray-200 text-gray-800 max-w-[80%] shadow-sm"
        }
      >
        {thinking ? (
          <div className="space-y-2">
            <div className="h-4 w-40 bg-gray-200 rounded animate-pulse" />
            <div className="h-4 w-64 bg-gray-200 rounded animate-pulse" />
          </div>
        ) : (
          <div className="text-sm leading-7 break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ""}</ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <Avatar className="mt-1 order-2 ml-3">
          <AvatarFallback className="bg-gradient-to-br from-blue-500 to-purple-600 text-white font-medium">我</AvatarFallback>
        </Avatar>
      )}
    </article>
  );
};

export default ChatMessage;
