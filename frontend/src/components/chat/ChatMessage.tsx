
/* eslint-disable @typescript-eslint/no-explicit-any */
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, Brain, ChevronDown, ChevronRight, Download, Maximize2, Minimize2 } from "lucide-react";
import { useStreamMarkdownBuffer } from "@/hooks/useStreamMarkdownBuffer";
import { useSmoothTyping } from "@/hooks/useSmoothTyping";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

export type ChatRole = "user" | "assistant";

export interface ChatMessageProps {
  role: ChatRole;
  content: string;
  status?: "pending" | "streaming" | "completed" | "stopped" | "failed";
  thinking?: boolean;
  thinkingFinished?: boolean;
}

const ThinkingProcess: React.FC<{ thoughts: string[]; thinkingFinished?: boolean }> = ({ thoughts, thinkingFinished }) => {
  const [isOpen, setIsOpen] = React.useState(true);

  React.useEffect(() => {
    if (thinkingFinished) {
      setIsOpen(false);
    }
  }, [thinkingFinished]);

  if (thoughts.length === 0) return null;

  return (
    <div className="mb-4">
      <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
        <CollapsibleTrigger className="flex items-center gap-2 text-xs font-medium text-primary hover:text-primary/80 transition-colors group">
          <div className="flex items-center gap-1.5 bg-primary/10 px-2 py-1 rounded-md border border-primary/20 group-hover:bg-primary/15 transition-colors">
            <Brain size={14} className="text-primary" />
            <span>深度思考</span>
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 pl-3 border-l-2 border-primary/20 space-y-1.5">
          {thoughts.map((thought, index) => (
            <div key={index} className="text-xs text-muted-foreground leading-relaxed">
              {thought}
            </div>
          ))}
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
};

const parseContent = (content: string) => {
  const lines = content.split("\n");
  const thoughts: string[] = [];
  const answerLines: string[] = [];
  let isCollectingThoughts = true;

  for (const line of lines) {
    const trimmedLine = line.trim();
    // 识别思维过程的标识符
    if (
      isCollectingThoughts &&
      (
        trimmedLine.startsWith("【计划】") ||
        trimmedLine.startsWith("【计划") ||
        trimmedLine.startsWith("【步骤】") ||
        trimmedLine.startsWith("【进行中】") ||
        trimmedLine.startsWith("【已完成】") ||
        /^Step\d+\s*:/.test(trimmedLine)
      )
    ) {
      thoughts.push(trimmedLine);
    } else if (isCollectingThoughts && thoughts.length > 0 && trimmedLine === "") {
      // 思维过程中的空行跳过
      continue;
    } else {
      // 一旦遇到非思维标识符的内容，后续全部视为正式回答
      if (trimmedLine !== "" || !isCollectingThoughts) {
        isCollectingThoughts = false;
        answerLines.push(line);
      }
    }
  }

  return {
    thoughts,
    answer: answerLines.join("\n").trim(),
  };
};

function normalizeMarkdownFence(answer: string): string {
  const text = (answer || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return text;

  // 解包任意位置的 ```markdown / ```md 代码块，避免被当作“代码展示”而非“文档渲染”。
  // 支持“先解释一句，再给 markdown 代码块”的常见模型输出形态。
  let normalized = text.replace(/```(?:markdown|md)\s*\n([\s\S]*?)```/gi, "$1");

  // 处理流式中间态：若开头围栏已到达但结尾围栏未到达，先移除开头围栏，降低黑框概率。
  normalized = normalized.replace(/^\s*```(?:markdown|md)\s*\n/i, "");

  // 处理尾部孤立结束围栏（流式拼接或模型输出噪音）。
  normalized = normalized.replace(/\n```[\t ]*$/i, "");

  return normalized;
}

function extractMarkdownTables(md: string): string[] {
  const text = (md || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return [];

  const lines = text.split("\n");
  const tables: string[] = [];
  let i = 0;

  const isRow = (s: string) => (s.match(/\|/g) || []).length >= 2;
  const isDivider = (s: string) => /^\s*\|?[\s:-]+(\|[\s:-]+)+\|?\s*$/.test(s);

  while (i < lines.length - 1) {
    const header = lines[i];
    const divider = lines[i + 1];

    if (isRow(header) && isDivider(divider)) {
      const buf = [header, divider];
      i += 2;
      while (i < lines.length && isRow(lines[i]) && lines[i].trim() !== "") {
        buf.push(lines[i]);
        i += 1;
      }
      tables.push(buf.join("\n"));
      continue;
    }
    i += 1;
  }

  return tables;
}

function markdownTableToTsv(tableMarkdown: string): string {
  const lines = (tableMarkdown || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  if (lines.length < 2) return tableMarkdown || "";

  const rows: string[][] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    // 跳过分隔行
    if (/^\|?[\s:-]+(\|[\s:-]+)+\|?$/.test(line)) continue;
    const normalized = line.replace(/^\|/, "").replace(/\|$/, "");
    const cols = normalized.split("|").map((c) => c.trim());
    rows.push(cols);
  }
  return rows.map((r) => r.join("\t")).join("\n");
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  role,
  content,
  status,
  thinking,
  thinkingFinished,
}) => {
  const isUser = role === "user";
  const [copiedCode, setCopiedCode] = React.useState<string | null>(null);
  const [copiedMessage, setCopiedMessage] = React.useState(false);
  const [copiedTableIdx, setCopiedTableIdx] = React.useState<number | null>(null);
  const [expandedTables, setExpandedTables] = React.useState<Record<number, boolean>>({});

  const displayedContent = content;

  const { thoughts, answer } = React.useMemo(() => {
    if (isUser) return { thoughts: [], answer: displayedContent };
    return parseContent(displayedContent);
  }, [displayedContent, isUser]);

  const normalizedAnswer = React.useMemo(() => normalizeMarkdownFence(answer), [answer]);

  const { stableMarkdown, pendingText, hasUnclosedFence } = useStreamMarkdownBuffer(
    normalizedAnswer,
    !isUser && Boolean(thinking)
  );
  const typedPendingText = useSmoothTyping(pendingText, !isUser && Boolean(thinking));
  const tableBlocks = React.useMemo(
    () => extractMarkdownTables(stableMarkdown || normalizedAnswer || ""),
    [stableMarkdown, normalizedAnswer]
  );
  const tableRenderIndexRef = React.useRef(0);

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  const handleCopyTable = async (tableIdx: number) => {
    const tableText = tableBlocks[tableIdx] || "";
    if (!tableText.trim()) return;
    try {
      await navigator.clipboard.writeText(tableText);
      setCopiedTableIdx(tableIdx);
      setTimeout(() => setCopiedTableIdx(null), 1500);
    } catch (error) {
      console.error("复制表格失败:", error);
    }
  };

  const handleDownloadTable = (tableIdx: number) => {
    const tableText = tableBlocks[tableIdx] || "";
    if (!tableText.trim()) return;
    const tsv = markdownTableToTsv(tableText);
    const blob = new Blob([tsv], { type: "text/tab-separated-values;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `table-${tableIdx + 1}.tsv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const toggleTableExpanded = (tableIdx: number) => {
    setExpandedTables((prev) => ({ ...prev, [tableIdx]: !prev[tableIdx] }));
  };

  const handleCopyMessage = async () => {
    const textToCopy = isUser ? displayedContent : normalizedAnswer;
    if (!textToCopy.trim()) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedMessage(true);
      setTimeout(() => setCopiedMessage(false), 2000);
    } catch (error) {
      console.error("复制消息失败:", error);
    }
  };

  tableRenderIndexRef.current = 0;

  return (
    <article className={`group/message flex w-full flex-col ${isUser ? "items-end" : "items-start"}`}>
      {!isUser && (
        <div className="mb-2 flex items-center gap-2 px-1">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-[#121629] text-[10px] font-bold text-white shadow-sm dark:bg-white dark:text-[#121629]">
            奇
          </span>
          <span className="text-xs font-medium text-muted-foreground">奇点AI</span>
        </div>
      )}
      <div
        className={
          isUser
            ? "max-w-[82%] rounded-[1.35rem] rounded-br-md bg-[#121629] px-4 py-3 text-white shadow-[0_12px_28px_-18px_rgba(18,22,41,0.8)] dark:bg-white dark:text-[#121629]"
            : "max-w-full rounded-[1.5rem] rounded-tl-md border border-white/80 bg-white/75 px-5 py-4 text-foreground shadow-[0_14px_42px_-30px_rgba(31,41,70,0.35)] backdrop-blur dark:border-white/[0.08] dark:bg-white/[0.045]"
        }
      >
        {thinking && !displayedContent ? (
          <div className="space-y-2">
            <div className="h-4 w-40 bg-muted rounded animate-pulse" />
            <div className="h-4 w-64 bg-muted rounded animate-pulse" />
          </div>
        ) : (
          <div className={`text-sm leading-7 break-words ${isUser ? 'prose-invert' : ''}`}>
            {!isUser && <ThinkingProcess thoughts={thoughts} thinkingFinished={thinkingFinished} />}
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkBreaks, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");
                  const language = match ? match[1] : "";

                  return !inline && match ? (
                    <div className="relative group my-4">
                      <div className="flex items-center justify-between bg-neutral-800 text-neutral-200 px-4 py-2 rounded-t-lg text-xs font-mono">
                        <span>{language}</span>
                        <button
                          onClick={() => handleCopyCode(codeString)}
                          className="flex items-center gap-1 hover:bg-neutral-700 px-2 py-1 rounded transition-colors"
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
                            : "bg-muted text-foreground font-medium"
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
                          : "text-accent hover:text-primary underline"
                      }`}
                    >
                      {children}
                    </a>
                  );
                },
                blockquote({ children }: any) {
                  return (
                  <blockquote className={`border-l-4 pl-4 py-2 my-2 italic ${
                    isUser ? "border-white/40" : "border-border"
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
                  const tableIdx = tableRenderIndexRef.current++;
                  const isCopied = copiedTableIdx === tableIdx;
                  const isExpanded = Boolean(expandedTables[tableIdx]);
                  return (
                    <div className="my-4 overflow-hidden rounded-xl border border-border">
                      {!isUser && (
                        <div className="flex items-center justify-between border-b border-border bg-muted px-3 py-2">
                          <span className="text-sm font-semibold text-foreground">表格</span>
                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() => handleCopyTable(tableIdx)}
                              className="inline-flex items-center justify-center rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-background transition-colors"
                              title="复制该表格"
                              aria-label="复制该表格"
                            >
                              {isCopied ? <Check size={13} /> : <Copy size={13} />}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDownloadTable(tableIdx)}
                              className="inline-flex items-center justify-center rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-background transition-colors"
                              title="下载 TSV"
                              aria-label="下载 TSV"
                            >
                              <Download size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={() => toggleTableExpanded(tableIdx)}
                              className="inline-flex items-center justify-center rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-background transition-colors"
                              title={isExpanded ? "收起表格" : "展开表格"}
                              aria-label={isExpanded ? "收起表格" : "展开表格"}
                            >
                              {isExpanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                            </button>
                          </div>
                        </div>
                      )}
                      <div className={`${isExpanded ? "overflow-auto" : "max-h-[360px] overflow-auto"}`}>
                        <table className="min-w-full divide-y divide-border">
                          {children}
                        </table>
                      </div>
                    </div>
                  );
                },
                thead({ children }: any) {
                  return <thead className="bg-muted">{children}</thead>;
                },
                th({ children }: any) {
                  return (
                    <th className="px-4 py-2 text-left text-xs font-semibold text-foreground border border-border">
                      {children}
                    </th>
                  );
                },
                td({ children }: any) {
                  return (
                    <td className="px-4 py-2 text-sm text-foreground border border-border">
                      {children}
                    </td>
                  );
                },
              }}
            >
              {stableMarkdown || ""}
            </ReactMarkdown>
            {!isUser && typedPendingText && (
              <pre className="whitespace-pre-wrap break-words text-sm leading-7 mt-2 text-muted-foreground">
                {typedPendingText}
              </pre>
            )}
            {!isUser && hasUnclosedFence && (
              <div className="text-xs text-muted-foreground mt-1">代码块生成中，已暂时使用纯文本显示。</div>
            )}
          </div>
        )}
      </div>
      {(displayedContent.trim() || (!isUser && (status === "stopped" || status === "failed"))) && (
        <div className={`mt-1.5 flex items-center gap-2 ${isUser ? "mr-1" : "ml-1"}`}>
          {!isUser && status === "stopped" && (
            <span className="text-[10px] text-muted-foreground">已停止生成</span>
          )}
          {!isUser && status === "failed" && (
            <span className="text-[10px] text-destructive">生成未完成</span>
          )}
          {displayedContent.trim() && (
            <button
              type="button"
              onClick={handleCopyMessage}
              className="inline-flex items-center justify-center rounded-md p-1.5 text-muted-foreground opacity-100 transition-[opacity,color,background-color] hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/20 sm:opacity-0 sm:group-hover/message:opacity-100 sm:group-focus-within/message:opacity-100"
              title={copiedMessage ? "已复制" : "复制消息"}
              aria-label={copiedMessage ? "消息已复制" : "复制消息"}
            >
              {copiedMessage ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
        </div>
      )}
    </article>
  );
};

export default ChatMessage;
