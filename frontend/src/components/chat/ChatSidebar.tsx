import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageSquare, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
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
  onSelect: (conversation: Conversation) => void;
  onRename: (conversation: Conversation) => void;
  onDelete: (conversation: Conversation) => void;
  loading?: boolean;
}

export const ChatSidebarContent: React.FC<ChatSidebarProps> = ({
  onNewChat,
  conversations,
  activeConversationId,
  onSelect,
  onRename,
  onDelete,
  loading = false,
}) => {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: conversations.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 8,
  });

  return (
    <div className="flex h-full min-h-0 flex-col px-4 pb-3">
      <div className="shrink-0 pb-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-xs font-medium text-primary-foreground transition-[background-color,transform] hover:-translate-y-0.5 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sidebar-ring/25 motion-reduce:transform-none sm:min-h-9"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          新建对话
        </button>
      </div>

      <SidebarGroup className="min-h-0 flex-1 px-0 py-0">
          <SidebarGroupLabel className="mb-1 px-2 text-[11px] font-medium">
            最近对话
          </SidebarGroupLabel>

          <div
            ref={parentRef}
            className="-mr-4 min-h-0 w-auto flex-1 overflow-y-auto overflow-x-hidden pr-4"
          >
            {loading ? (
              <div className="space-y-1 px-0.5 pt-1">
                {Array.from({ length: 4 }).map((_, index) => (
                  <div key={index} className="h-10 animate-pulse rounded-lg bg-sidebar-accent motion-reduce:animate-none" />
                ))}
              </div>
            ) : conversations.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <p className="text-xs font-medium text-foreground">
                  还没有历史对话
                </p>
                <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
                  发送第一条消息后会自动保存
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
                        className={`group relative flex h-full w-full items-center rounded-lg transition-colors ${
                          active
                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                            : "hover:bg-sidebar-accent/70"
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => onSelect(item)}
                          className="flex h-full min-w-0 flex-1 items-center gap-2 rounded-lg px-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
                        >
                          <span className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-lg", active ? "bg-primary text-primary-foreground" : "bg-background text-muted-foreground")}>
                            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1 truncate text-xs font-medium">{item.title}</span>
                        </button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              className="mr-0.5 grid h-11 w-11 shrink-0 place-items-center rounded-lg text-muted-foreground opacity-100 hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
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
    </div>
  );
};
