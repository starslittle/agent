import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { matchPath, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import {
  deleteConversation as deleteConversationRequest,
  listConversations,
  renameConversation as renameConversationRequest,
  type Conversation,
} from "@/lib/chat-api";
import {
  WorkspaceConversationsContext,
  type WorkspaceConversationsValue,
} from "@/components/workspace/workspace-conversations-context";

export function WorkspaceConversationsProvider({ children }: { children: ReactNode }) {
  const { user, csrfToken } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(Boolean(user));
  const [newChatVersion, setNewChatVersion] = useState(0);

  const activeConversationId = matchPath(
    { path: "/chat/:conversationId", end: true },
    location.pathname,
  )?.params.conversationId ?? null;

  const refreshConversations = useCallback(async () => {
    if (!user) {
      setConversations([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const response = await listConversations();
      setConversations(response.items);
    } catch (error) {
      toast.error((error as Error).message || "无法加载会话列表");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  const startNewChat = useCallback(() => {
    setNewChatVersion((current) => current + 1);
    navigate("/");
  }, [navigate]);

  const selectConversation = useCallback((conversation: Conversation) => {
    navigate(`/chat/${encodeURIComponent(conversation.id)}`);
  }, [navigate]);

  const upsertConversation = useCallback((conversation: Conversation) => {
    setConversations((current) => [
      conversation,
      ...current.filter((item) => item.id !== conversation.id),
    ]);
  }, []);

  const renameConversation = useCallback(async (conversation: Conversation) => {
    const title = window.prompt("为这段对话输入新标题", conversation.title)?.trim();
    if (!title || title === conversation.title) return;

    try {
      const updated = await renameConversationRequest(conversation.id, title, csrfToken);
      setConversations((current) =>
        current.map((item) => item.id === updated.id ? { ...item, ...updated } : item),
      );
    } catch (error) {
      toast.error((error as Error).message || "重命名失败");
    }
  }, [csrfToken]);

  const deleteConversation = useCallback(async (conversation: Conversation) => {
    if (!window.confirm(`确定删除“${conversation.title}”吗？`)) return;

    try {
      await deleteConversationRequest(conversation.id, csrfToken);
      setConversations((current) => current.filter((item) => item.id !== conversation.id));
      if (conversation.id === activeConversationId) startNewChat();
      toast.success("会话已删除");
    } catch (error) {
      toast.error((error as Error).message || "删除失败");
    }
  }, [activeConversationId, csrfToken, startNewChat]);

  const value = useMemo<WorkspaceConversationsValue>(() => ({
    conversations,
    loading,
    activeConversationId,
    newChatVersion,
    startNewChat,
    selectConversation,
    renameConversation,
    deleteConversation,
    refreshConversations,
    upsertConversation,
  }), [
    activeConversationId,
    conversations,
    deleteConversation,
    loading,
    newChatVersion,
    refreshConversations,
    renameConversation,
    selectConversation,
    startNewChat,
    upsertConversation,
  ]);

  return (
    <WorkspaceConversationsContext.Provider value={value}>
      {children}
    </WorkspaceConversationsContext.Provider>
  );
}
