import React from "react";
import ChatContainer from "@/components/chat/ChatContainer";

const Index = () => {
  return (
    <div className="h-screen w-full bg-background flex flex-col overflow-hidden">
      <header className="border-b flex-shrink-0">
        <div className="container py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-primary to-accent shadow flex items-center justify-center text-ongradient text-sm font-bold" aria-label="奇点AI Logo">奇</div>
            <span className="text-lg font-semibold">奇点AI</span>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden w-full relative">
        <ChatContainer />
      </main>
    </div>
  );
};

export default Index;
