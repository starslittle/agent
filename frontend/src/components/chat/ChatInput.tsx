
import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
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
    <div className="w-full space-y-2">
      {/* 模式切换按钮：深度思考 */}
      <div className="flex gap-2 justify-start">
        <button
          type="button"
          onClick={() => setDeep(!deep)}
          aria-pressed={deep}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200",
            deep ? "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-md" : "bg-muted text-muted-foreground hover:bg-muted/70"
          )}
          title="切换深度思考"
        >
          <Brain size={15} />
          深度思考
        </button>
      </div>

      {/* 对话框 */}
      <div className="flex items-center gap-2 py-2 px-2 bg-card rounded-2xl border border-border shadow-sm">
        {/* 上传图片按钮 */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 w-9 h-9 rounded-full bg-muted hover:bg-muted/70 flex items-center justify-center transition-colors"
          aria-label="上传图片"
          title="上传图片"
        >
          <Plus size={20} className="text-gray-600" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        {/* 输入框 */}
        <Textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onInput={autosize}
          rows={1}
          placeholder="输入消息... Enter 发送，Shift+Enter 换行"
          className="flex-1 max-h-20 overflow-y-auto border-0 shadow-none focus-visible:ring-0 bg-transparent px-0 text-sm leading-5 text-gray-800 min-h-[24px]"
          aria-label="聊天输入"
        />

        {/* 发送/停止按钮 */}
        <button
          disabled={!loading && (sending || (!value.trim() && !file))}
          onClick={loading ? onStop : handleSend}
          className={cn(
            "flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed",
            "bg-gradient-to-r from-primary to-accent hover:from-primary/90 hover:to-accent/90"
          )}
          title={loading ? "停止生成" : "发送消息"}
        >
          {loading ? (
            <Square size={14} className="text-white fill-white" />
          ) : (
            <Send size={18} className="text-white" />
          )}
        </button>
      </div>

      {file && (
        <div className="px-4 text-xs text-gray-500 truncate" aria-live="polite">
          已选择图片：{file.name}
        </div>
      )}
    </div>
  );
};

export default ChatInput;
