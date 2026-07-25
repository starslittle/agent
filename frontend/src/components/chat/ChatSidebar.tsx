import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { MessageSquare, Plus, Search } from "lucide-react";
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
}

export const ChatSidebar: React.FC<ChatSidebarProps> = ({ onNewChat }) => {
  const parentRef = useRef<HTMLDivElement>(null);

  // 临时模拟历史记录；接入真实会话接口后移除
  const historyItems = Array.from({ length: 5 }, (_, i) => ({
    id: i,
    title: `历史会话 ${i + 1}`,
    date: new Date().toLocaleDateString()
  }));

  const rowVirtualizer = useVirtualizer({
    count: historyItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 56, // 每个列表项预估高度 56px
    overscan: 10, // 视口外多渲染几项，防止快速滚动时出现白屏
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
            <span>{historyItems.length}</span>
          </SidebarGroupLabel>

          <div
            ref={parentRef}
            className="w-full flex-1 overflow-auto overflow-x-hidden"
            style={{ height: "calc(100vh - 250px)" }}
          >
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: '100%',
                position: 'relative',
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const item = historyItems[virtualRow.index];
                return (
                  <button
                    type="button"
                    key={virtualRow.index}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className="group flex w-full items-center gap-3 rounded-xl px-3 text-left transition hover:bg-white/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 dark:hover:bg-white/[0.06]"
                  >
                    <span className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-white/70 text-muted-foreground shadow-sm transition group-hover:text-primary dark:bg-white/[0.06]">
                      <MessageSquare className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium">{item.title}</span>
                      <span className="mt-0.5 block text-[10px] text-muted-foreground">{item.date}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="px-4 pb-5">
        <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-white/50 px-3 py-3 text-muted-foreground dark:bg-white/[0.035]">
          <Search className="h-4 w-4 flex-shrink-0" />
          <p className="text-[11px] leading-4">
            会话搜索与真实历史记录将在下一阶段接入
          </p>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
};
