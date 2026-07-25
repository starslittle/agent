import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageSquare, Pencil, Plus, Search, Trash2 } from "lucide-react";
import type { Conversation } from "@/lib/chat-api";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarGroup,
  SidebarGroupLabel
} from "@/components/ui/sidebar";

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

export const ChatSidebar: React.FC<ChatSidebarProps> = ({
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
    <Sidebar
      variant="sidebar"
      className="border-r border-border/60 bg-[#eef1f8] dark:bg-[#0d101c]"
    >
      <SidebarHeader className="gap-5 px-4 pb-3 pt-5">
        <div className="flex items-center gap-3 px-1">
          <div className="grid h-10 w-10 place-items-center rounded-[0.9rem] border border-violet-200/80 bg-white/80 shadow-sm dark:border-white/10 dark:bg-white/5">
            <span className="bg-gradient-to-tr from-violet-600 to-blue-500 bg-clip-text text-sm font-bold text-transparent dark:from-violet-300 dark:to-blue-300">
              奇
            </span>
          </div>
          <div>
            <p className="text-[15px] font-semibold tracking-tight">奇点AI</p>
            <p className="text-[9px] tracking-[0.18em] text-muted-foreground">
              QIDIAN WORKSPACE
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onNewChat}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#121629] px-4 text-sm font-medium text-white shadow-[0_14px_28px_-18px_rgba(18,22,41,0.75)] transition hover:-translate-y-0.5 hover:bg-[#1d2340] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/20 motion-reduce:transform-none dark:bg-white dark:text-[#121629] dark:hover:bg-white/90"
        >
          <Plus className="h-4 w-4" />
          新建对话
        </button>
      </SidebarHeader>
      <SidebarContent className="px-2">
        <SidebarGroup className="min-h-0 flex-1 px-2">
          <SidebarGroupLabel className="mb-1 justify-between px-2 text-[11px] font-medium">
            <span>最近对话</span>
            <span>{conversations.length}</span>
          </SidebarGroupLabel>

          <div
            ref={parentRef}
            className="w-full flex-1 overflow-auto overflow-x-hidden"
            style={{ height: "calc(100vh - 250px)" }}
          >
            {loading ? (
              <div className="space-y-2 px-2 pt-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index} className="h-14 animate-pulse rounded-xl bg-white/50 dark:bg-white/[0.04]" />
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
                        role="button"
                        tabIndex={0}
                        onClick={() => onSelect(item)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            onSelect(item);
                          }
                        }}
                        className={`group relative flex h-full w-full items-center gap-3 rounded-xl px-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
                          active
                            ? "bg-white text-foreground shadow-sm dark:bg-white/[0.08]"
                            : "hover:bg-white/70 dark:hover:bg-white/[0.06]"
                        }`}
                      >
                        <span className={`grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg shadow-sm transition ${
                          active
                            ? "bg-[#121629] text-white dark:bg-white dark:text-[#121629]"
                            : "bg-white/70 text-muted-foreground group-hover:text-primary dark:bg-white/[0.06]"
                        }`}>
                          <MessageSquare className="h-3.5 w-3.5" />
                        </span>
                        <span className="min-w-0 flex-1 pr-12">
                          <span className="block truncate text-xs font-medium">{item.title}</span>
                          <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                            {item.last_message_preview || formatConversationDate(item.last_message_at || item.created_at)}
                          </span>
                        </span>
                        <span className="absolute right-2 flex items-center rounded-lg bg-inherit opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              onRename(item);
                            }}
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                            aria-label={`重命名${item.title}`}
                            title="重命名"
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              onDelete(item);
                            }}
                            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                            aria-label={`删除${item.title}`}
                            title="删除"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="px-4 pb-5">
        <label className="flex items-center gap-2 rounded-xl border border-border/50 bg-white/55 px-3 py-2.5 text-muted-foreground transition focus-within:border-primary/30 focus-within:ring-2 focus-within:ring-primary/10 dark:bg-white/[0.035]">
          <Search className="h-4 w-4 flex-shrink-0" />
          <input
            type="search"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索历史对话"
            className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
      </SidebarFooter>
    </Sidebar>
  );
};
