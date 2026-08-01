import { useEffect, useRef, useState } from "react";
import { LoaderCircle, MessageSquare, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { listConversations, type Conversation } from "@/lib/chat-api";

export function ConversationSearchDialog() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError("");

    const timer = window.setTimeout(() => {
      void listConversations(query)
        .then((response) => {
          if (!cancelled) setConversations(response.items);
        })
        .catch((requestError: Error) => {
          if (!cancelled) {
            setConversations([]);
            setError(requestError.message || "暂时无法搜索对话");
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, query.trim() ? 250 : 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query, retryKey]);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) setQuery("");
  };

  const handleSelect = (conversation: Conversation) => {
    setOpen(false);
    setQuery("");
    navigate(`/chat/${conversation.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DialogTrigger asChild>
            <button
              type="button"
              className="grid h-11 w-11 shrink-0 touch-manipulation place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
              aria-label="搜索对话"
            >
              <Search className="h-4 w-4" aria-hidden="true" />
            </button>
          </DialogTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">搜索对话</TooltipContent>
      </Tooltip>

      <DialogContent
        className="w-[calc(100%_-_2rem)] max-w-2xl gap-0 overflow-hidden rounded-2xl p-0 [&>button]:right-2 [&>button]:top-1.5 [&>button]:grid [&>button]:h-11 [&>button]:w-11 [&>button]:place-items-center [&>button]:rounded-xl"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
      >
        <DialogTitle className="sr-only">搜索对话</DialogTitle>
        <DialogDescription className="sr-only">
          输入关键词搜索历史对话，使用方向键选择结果并按回车打开。
        </DialogDescription>

        <Command shouldFilter={false} loop className="rounded-2xl bg-background">
          <CommandInput
            ref={inputRef}
            name="workspace-conversation-search"
            autoComplete="off"
            value={query}
            onValueChange={setQuery}
            placeholder="搜索对话…"
            aria-label="搜索对话"
            className="h-14 pr-12"
          />
          <CommandList className="max-h-[min(60dvh,32rem)] overscroll-contain px-3 pb-4 pt-2">
            {loading ? (
              <div
                className="flex min-h-32 items-center justify-center gap-2 text-sm text-muted-foreground"
                role="status"
                aria-live="polite"
              >
                <LoaderCircle
                  className="h-4 w-4 animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
                正在搜索…
              </div>
            ) : error ? (
              <div className="flex min-h-32 flex-col items-center justify-center px-6 text-center">
                <p className="text-sm font-medium text-foreground">搜索失败</p>
                <p className="mt-1 text-xs text-muted-foreground" role="alert">
                  {error}
                </p>
                <button
                  type="button"
                  onClick={() => setRetryKey((value) => value + 1)}
                  className="mt-4 min-h-11 touch-manipulation rounded-xl border border-border px-4 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  重试
                </button>
              </div>
            ) : conversations.length === 0 ? (
              <CommandEmpty className="min-h-32 px-6 py-8 text-center">
                <p className="text-sm font-medium text-foreground">
                  {query.trim() ? "没有找到相关对话" : "还没有历史对话"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {query.trim() ? "换个关键词试试" : "发送第一条消息后会自动保存"}
                </p>
              </CommandEmpty>
            ) : (
              <CommandGroup heading={query.trim() ? "搜索结果" : "最近对话"}>
                {conversations.map((conversation) => (
                  <CommandItem
                    key={conversation.id}
                    value={conversation.id}
                    onSelect={() => handleSelect(conversation)}
                    className="min-h-14 cursor-pointer touch-manipulation gap-3 rounded-xl px-3 py-2"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                      <MessageSquare className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">
                        {conversation.title}
                      </span>
                      {conversation.last_message_preview && (
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {conversation.last_message_preview}
                        </span>
                      )}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
