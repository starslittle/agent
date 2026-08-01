import { createContext, useContext } from "react";

import type { Conversation } from "@/lib/chat-api";

export interface WorkspaceConversationsValue {
  conversations: Conversation[];
  loading: boolean;
  activeConversationId: string | null;
  newChatVersion: number;
  startNewChat: () => void;
  selectConversation: (conversation: Conversation) => void;
  renameConversation: (conversation: Conversation) => Promise<void>;
  deleteConversation: (conversation: Conversation) => Promise<void>;
  refreshConversations: () => Promise<void>;
  upsertConversation: (conversation: Conversation) => void;
}

export const WorkspaceConversationsContext = createContext<WorkspaceConversationsValue | null>(null);

export function useWorkspaceConversations(): WorkspaceConversationsValue {
  const value = useContext(WorkspaceConversationsContext);
  if (!value) throw new Error("useWorkspaceConversations must be used inside WorkspaceConversationsProvider");
  return value;
}
