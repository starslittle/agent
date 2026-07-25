
import React, { useEffect, useRef, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Brain, Plus, Send, Square } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string, deepThinking: boolean) => void;
  loading?: boolean;
  onStop?: () => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, loading, onStop }) => {
  const [value, setValue] = useState("");
  const [deep, setDeep] = useState(false);
  // local sending state still useful for debounce/prevent double click
  const [sending, setSending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const autosize = () => {
    const el = taRef.current;
    if (!el) return;
    // 单行基础高度，随内容增高
    const base = 24; // 单行高度(px)
    const max = 160;
    el.style.height = "0px";
    const next = Math.min(Math.max(el.scrollHeight, base), max);
    el.style.height = `${next}px`;
  };

  useEffect(() => {
    autosize();
  }, [value]);

  const handleSend = () => {
    const text = value.trim();
    if (!text && !file) return;
    setSending(true);
    onSend(text || (file ? "[已附加图片]" : ""), deep);
    setValue("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setTimeout(() => setSending(false), 200);
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="w-full">
      <div className="rounded-[1.6rem] border border-white/90 bg-white/90 p-2.5 shadow-[0_20px_60px_-28px_rgba(31,41,70,0.4)] backdrop-blur-xl dark:border-white/10 dark:bg-[#111521]/90 dark:shadow-[0_20px_60px_-28px_rgba(0,0,0,0.9)]">
        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
            aria-label="上传图片"
            title="上传图片"
          >
            <Plus size={19} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />

          <Textarea
            ref={taRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            onInput={autosize}
            rows={1}
            placeholder="描述你想解决的问题…"
            className="min-h-[40px] max-h-32 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-1 py-2.5 text-sm leading-5 text-foreground shadow-none placeholder:text-muted-foreground/70 focus-visible:ring-0"
            aria-label="聊天输入"
          />

          <button
            type="button"
            disabled={!loading && (sending || (!value.trim() && !file))}
            onClick={loading ? onStop : handleSend}
            className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-xl bg-[#121629] text-white shadow-[0_10px_24px_-12px_rgba(18,22,41,0.8)] transition hover:-translate-y-0.5 hover:bg-[#1d2340] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-35 motion-reduce:transform-none dark:bg-white dark:text-[#121629] dark:hover:bg-white/90"
            title={loading ? "停止生成" : "发送消息"}
            aria-label={loading ? "停止生成" : "发送消息"}
          >
            {loading ? (
              <Square size={13} className="fill-current" />
            ) : (
              <Send size={17} />
            )}
          </button>
        </div>

        <div className="mt-1 flex items-center justify-between px-1">
          <button
            type="button"
            onClick={() => setDeep(!deep)}
            aria-pressed={deep}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-[11px] font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
              deep
                ? "bg-violet-500/10 text-violet-700 dark:text-violet-300"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
            title="切换深度思考"
          >
            <Brain size={13} />
            深度思考
            <span className={cn("h-1.5 w-1.5 rounded-full", deep ? "bg-violet-500" : "bg-muted-foreground/35")} />
          </button>
          <span className="pr-1 text-[10px] text-muted-foreground/70">
            Enter 发送 · Shift + Enter 换行
          </span>
        </div>
      </div>

      {file && (
        <div className="mt-2 truncate px-4 text-xs text-muted-foreground" aria-live="polite">
          已选择图片：{file.name}
        </div>
      )}
    </div>
  );
};

export default ChatInput;
