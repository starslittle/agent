import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageSquare, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import type { Conversation } from "@/lib/chat-api";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarGroup, SidebarGroupLabel } from "@/components/ui/sidebar";

interface ChatSidebarProps {
  onNewChat: () => void;
  conversations: Conversation[];
  activeConversationId?: string | null;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onSelect: (conversation: Conversation) => void;
  onRename: (conversation: Conversation) => void;
  onDelete: (conversation: Conversation) => void;
  loading?: boolean;
}

function formatConversationDate(value?: string): string {
  if (!value) return "刚刚";
  const date = new Date(value);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export const ChatSidebarContent: React.FC<ChatSidebarProps> = ({
  onNewChat,
  conversations,
  activeConversationId,
  searchQuery,
  onSearchChange,
  onSelect,
  onRename,
  onDelete,
  loading = false,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: conversations.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
  });

  return (
    <div className="flex h-full min-h-0 flex-col px-4 pb-3">
      <div className="shrink-0 pb-4">
        <button
          type="button"
          onClick={onNewChat}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-[background-color,transform] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sidebar-ring/25 motion-reduce:transform-none"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          新建对话
        </button>
      </div>

      <SidebarGroup className="min-h-0 flex-1 px-0 py-0">
          <SidebarGroupLabel className="mb-1 justify-between px-2 text-[11px] font-medium">
            <span>最近对话</span>
            <span>{conversations.length}</span>
          </SidebarGroupLabel>

          <div
            ref={parentRef}
            className="min-h-0 w-full flex-1 overflow-y-auto overflow-x-hidden"
          >
            {loading ? (
              <div className="space-y-2 px-2 pt-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index} className="h-14 animate-pulse rounded-xl bg-sidebar-accent" />
                ))}
              </div>
            ) : conversations.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <p className="text-xs font-medium text-foreground">
                  {searchQuery ? "没有找到相关对话" : "还没有历史对话"}
                </p>
                <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                  {searchQuery ? "换个关键词试试" : "发送第一条消息后会自动保存"}
                </p>
              </div>
            ) : (
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const item = conversations[virtualRow.index];
                  const active = item.id === activeConversationId;
                  return (
                    <div
                      key={item.id}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: `${virtualRow.size}px`,
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                      className="px-0.5 py-0.5"
                    >
                      <div
                        className={`group relative flex h-full w-full items-center rounded-xl transition-colors ${
                          active
                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                            : "hover:bg-sidebar-accent/70"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => onSelect(item)}
                          className="flex h-full min-w-0 flex-1 items-center gap-3 rounded-xl px-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                        >
                          <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg", active ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground")}>
                            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-medium">{item.title}</span>
                            <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                              {item.last_message_preview || formatConversationDate(item.last_message_at || item.created_at)}
                            </span>
                          </span>
                        </button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="mr-1 grid h-11 w-11 shrink-0 place-items-center rounded-xl text-muted-foreground opacity-100 hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                              aria-label={`${item.title}的更多操作`}
                            >
                              <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem className="min-h-11" onSelect={() => onRename(item)}>
                              <Pencil className="mr-2 h-4 w-4" aria-hidden="true" />重命名
                            </DropdownMenuItem>
                            <DropdownMenuItem className="min-h-11 text-destructive focus:text-destructive" onSelect={() => onDelete(item)}>
                              <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
      </SidebarGroup>

      <div className="shrink-0 pt-3">
        <label className="flex min-h-11 items-center gap-2 rounded-xl border border-border bg-background/60 px-3 text-muted-foreground transition-colors focus-within:border-primary focus-within:ring-2 focus-within:ring-sidebar-ring/20">
          <Search className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <input
            type="search"
            name="conversation-search"
            autoComplete="off"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索历史对话…"
            aria-label="搜索历史对话"
            className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
      </div>
    </div>
  );
};
