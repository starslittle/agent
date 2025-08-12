import React from "react";
import ChatContainer from "@/components/chat/ChatContainer";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container py-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-primary to-accent shadow flex items-center justify-center text-ongradient text-sm font-bold" aria-label="奇点AI Logo">奇</div>
            <span className="text-lg font-semibold">奇点AI</span>
          </div>
          {/* <nav className="hidden sm:block text-sm text-muted-foreground">
            <a href="#" className="hover:text-foreground transition-colors">关于</a>
          </nav> */}
        </div>
      </header>

      <main className="container py-8">
        <ChatContainer />
      </main>
    </div>
  );
};

export default Index;
