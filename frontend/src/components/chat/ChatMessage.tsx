
/* eslint-disable @typescript-eslint/no-explicit-any */
import React from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Bot, Copy, Check } from "lucide-react";
import { useSmoothTyping } from "@/hooks/useSmoothTyping";

export type ChatRole = "user" | "assistant";

export interface ChatMessageProps {
  role: ChatRole;
  content: string;
  thinking?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, thinking }) => {
  const isUser = role === "user";
  const [copiedCode, setCopiedCode] = React.useState<string | null>(null);

  // 始终调用 hook，但是在 hook 内部或使用结果时处理逻辑
  // 这里的策略是：始终计算 typedContent，但如果是用户消息，我们直接忽略计算结果使用原始 content
  // 这种方式虽然稍微多一点计算，但符合 React Rules of Hooks
  const typedContent = useSmoothTyping(content, thinking);
  const displayedContent = isUser ? content : typedContent;

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

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
          <div className={`text-sm leading-7 break-words ${isUser ? 'prose-invert' : ''}`}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");
                  const language = match ? match[1] : "";

                  return !inline && match ? (
                    <div className="relative group my-4">
                      <div className="flex items-center justify-between bg-gray-800 text-gray-200 px-4 py-2 rounded-t-lg text-xs font-mono">
                        <span>{language}</span>
                        <button
                          onClick={() => handleCopyCode(codeString)}
                          className="flex items-center gap-1 hover:bg-gray-700 px-2 py-1 rounded transition-colors"
                          title="复制代码"
                        >
                          {copiedCode === codeString ? (
                            <>
                              <Check size={14} />
                              <span>已复制</span>
                            </>
                          ) : (
                            <>
                              <Copy size={14} />
                              <span>复制</span>
                            </>
                          )}
                        </button>
                      </div>
                      <SyntaxHighlighter
                        style={vscDarkPlus}
                        language={language}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          borderTopLeftRadius: 0,
                          borderTopRightRadius: 0,
                          borderBottomLeftRadius: "0.5rem",
                          borderBottomRightRadius: "0.5rem",
                        }}
                        {...props}
                      >
                        {codeString}
                      </SyntaxHighlighter>
                    </div>
                  ) : (
                    <code
                      className={`${
                        isUser 
                          ? "bg-white/20 text-white" 
                          : "bg-gray-100 text-red-600"
                      } px-1.5 py-0.5 rounded text-xs font-mono`}
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
                p({ children }: any) {
                  return <p className="mb-2 last:mb-0">{children}</p>;
                },
                ul({ children }: any) {
                  return <ul className="list-disc list-outside ml-5 mb-2 space-y-1">{children}</ul>;
                },
                ol({ children }: any) {
                  return <ol className="list-decimal list-outside ml-5 mb-2 space-y-1">{children}</ol>;
                },
                li({ children }: any) {
                  return <li>{children}</li>;
                },
                a({ href, children }: any) {
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`${
                        isUser 
                          ? "text-white underline hover:text-gray-200" 
                          : "text-blue-600 hover:text-blue-800 underline"
                      }`}
                    >
                      {children}
                    </a>
                  );
                },
                blockquote({ children }: any) {
                  return (
                    <blockquote className={`border-l-4 pl-4 py-2 my-2 italic ${
                      isUser ? "border-white/40" : "border-gray-300"
                    }`}>
                      {children}
                    </blockquote>
                  );
                },
                h1({ children }: any) {
                  return <h1 className="text-xl font-bold mb-2 mt-4">{children}</h1>;
                },
                h2({ children }: any) {
                  return <h2 className="text-lg font-bold mb-2 mt-3">{children}</h2>;
                },
                h3({ children }: any) {
                  return <h3 className="text-base font-bold mb-2 mt-2">{children}</h3>;
                },
                table({ children }: any) {
                  return (
                    <div className="overflow-x-auto my-4">
                      <table className="min-w-full divide-y divide-gray-300 border border-gray-300">
                        {children}
                      </table>
                    </div>
                  );
                },
                thead({ children }: any) {
                  return <thead className="bg-gray-50">{children}</thead>;
                },
                th({ children }: any) {
                  return (
                    <th className="px-4 py-2 text-left text-xs font-semibold text-gray-900 border border-gray-300">
                      {children}
                    </th>
                  );
                },
                td({ children }: any) {
                  return (
                    <td className="px-4 py-2 text-sm text-gray-700 border border-gray-300">
                      {children}
                    </td>
                  );
                },
              }}
            >
              {displayedContent || ""}
            </ReactMarkdown>
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
