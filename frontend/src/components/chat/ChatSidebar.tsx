import React, { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarGroup,
  SidebarGroupLabel
} from "@/components/ui/sidebar";

export const ChatSidebar = () => {
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
    <Sidebar variant="sidebar">
      <SidebarHeader>
        <div className="p-4 text-lg font-bold">会话历史</div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>所有记录 ({historyItems.length})</SidebarGroupLabel>

          {/* 虚拟列表容器，必须有固定高度或填满父元素并允许滚动 */}
          <div
            ref={parentRef}
            className="w-full flex-1 overflow-auto overflow-x-hidden"
            style={{ height: "calc(100vh - 120px)" }}
          >
            {/* 内部占位容器，高度为所有项的总高度 */}
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                width: '100%',
                position: 'relative',
              }}
            >
              {/* 只渲染当前视口内可见的项 */}
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const item = historyItems[virtualRow.index];
                return (
                  <div
                    key={virtualRow.index}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                    className="px-4 py-2 border-b border-border/40 hover:bg-accent hover:text-accent-foreground cursor-pointer flex flex-col justify-center transition-colors"
                  >
                    <div className="text-sm font-medium truncate">{item.title}</div>
                    <div className="text-xs text-muted-foreground mt-1">{item.date}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
};
