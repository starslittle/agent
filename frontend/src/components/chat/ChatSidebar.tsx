import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Bot, MessageSquare, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import type { Conversation } from "@/lib/chat-api";
import { QidianWordmark } from "@/brand/QidianMark";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
      className="border-r border-sidebar-border bg-sidebar"
    >
      <SidebarHeader className="gap-5 px-4 pb-3 pt-5">
        <QidianWordmark />

        <nav className="space-y-1" aria-label="工作区导航">
          <Link
            to="/"
            className="flex min-h-11 items-center gap-3 rounded-xl bg-sidebar-accent px-3 text-xs font-medium text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
          >
            <MessageSquare className="h-4 w-4" aria-hidden="true" />
            对话
          </Link>
          <Link
            to="/agent-runs"
            className="flex min-h-11 items-center gap-3 rounded-xl px-3 text-xs text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
          >
            <Bot className="h-4 w-4" aria-hidden="true" />
            Agent Runs
          </Link>
        </nav>

        <button
          type="button"
          onClick={onNewChat}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-[background-color,transform] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sidebar-ring/25 motion-reduce:transform-none"
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
            style={{ height: "calc(100dvh - 350px)" }}
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
      </SidebarContent>
      <SidebarFooter className="px-4 pb-5">
        <label className="flex min-h-11 items-center gap-2 rounded-xl border border-border bg-background/60 px-3 text-muted-foreground transition-colors focus-within:border-primary focus-within:ring-2 focus-within:ring-sidebar-ring/20">
          <Search className="h-4 w-4 flex-shrink-0" />
          <input
            type="search"
            name="conversation-search"
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
