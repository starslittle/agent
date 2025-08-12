
import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { Plus, Send } from "lucide-react";

interface ChatInputProps {
  onSend: (text: string, deepThinking: boolean) => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend }) => {
  const [value, setValue] = useState("");
  const [deep, setDeep] = useState(false);
  const [sending, setSending] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const autosize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
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
      {/* 深度思考按钮在上方 */}
      <div className="flex justify-start">
        <button
          type="button"
          onClick={() => setDeep((d) => !d)}
          aria-pressed={deep}
          className={cn(
            "px-3 py-1.5 rounded-full text-sm font-medium transition-all duration-200",
            deep
              ? "bg-gradient-to-r from-primary to-accent text-white shadow-md"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          )}
          title="切换深度思考"
        >
          🧠 深度思考
        </button>
      </div>

      {/* 对话框 */}
      <div className="flex items-end gap-2 p-3 bg-white rounded-2xl border border-gray-200 shadow-sm">
        {/* 上传图片按钮 */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="flex-shrink-0 w-9 h-9 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center transition-colors"
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
          className="flex-1 max-h-40 overflow-y-auto resize-none border-0 shadow-none focus-visible:ring-0 bg-transparent px-0 text-sm leading-5 text-gray-800 placeholder:text-gray-400"
          aria-label="聊天输入"
        />

        {/* 发送按钮 */}
        <button
          disabled={sending || (!value.trim() && !file)}
          onClick={handleSend}
          className="flex-shrink-0 w-9 h-9 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 flex items-center justify-center transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send size={18} className="text-white" />
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
