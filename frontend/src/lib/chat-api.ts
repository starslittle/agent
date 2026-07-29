export interface Conversation {
  id: string;
  title: string;
  agent_name: string;
  status: "active" | "archived" | "deleted";
  last_message_preview?: string;
  last_message_at?: string;
  created_at: string;
  updated_at: string;
}

export interface StoredMessage {
  id: string;
  conversation_id: string;
  client_message_id?: string;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "streaming" | "completed" | "stopped" | "failed";
  sequence_id: number;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

interface ConversationListResponse {
  items: Conversation[];
  next_before?: string | null;
}

export interface MessageListResponse {
  items: StoredMessage[];
  next_before?: number | null;
}

export type ConversationStreamEvent =
  | {
      type: "meta";
      conversation_id: string;
      user_message_id: string;
      assistant_message_id: string;
      run_id: string;
      execution_id?: string;
      protocol_version?: number;
      title: string;
    }
  | {
      type: "delta";
      data?: string;
      isThinking?: boolean;
      thinkingFinished?: boolean;
    }
  | {
      type: "done";
      message_id?: string;
      status?: string;
    }
  | {
      type: "error";
      message?: string;
    };

function apiBase(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const value = env.VITE_API_BASE as string | undefined;
  return value ? value.replace(/\/$/, "") : "";
}

async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  csrfToken?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      error?: string;
      message?: string;
    };
    throw new Error(chatErrorMessage(payload.error, payload.message));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function listConversations(
  query = "",
  limit = 50,
): Promise<ConversationListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query.trim()) params.set("q", query.trim());
  return apiRequest<ConversationListResponse>(
    `/api/v1/conversations?${params.toString()}`,
  );
}

export async function createConversation(
  csrfToken: string,
  agentName?: string,
): Promise<Conversation> {
  return apiRequest<Conversation>(
    "/api/v1/conversations",
    {
      method: "POST",
      body: JSON.stringify({ agent_name: agentName || "default_llm_agent" }),
    },
    csrfToken,
  );
}

export async function getConversation(id: string): Promise<Conversation> {
  return apiRequest<Conversation>(`/api/v1/conversations/${encodeURIComponent(id)}`);
}

export async function listMessages(
  conversationID: string,
  limit = 50,
  before?: number,
): Promise<MessageListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (before !== undefined) params.set("before", String(before));
  return apiRequest<MessageListResponse>(
    `/api/v1/conversations/${encodeURIComponent(conversationID)}/messages?${params.toString()}`,
  );
}

export async function renameConversation(
  conversationID: string,
  title: string,
  csrfToken: string,
): Promise<Conversation> {
  return apiRequest<Conversation>(
    `/api/v1/conversations/${encodeURIComponent(conversationID)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    },
    csrfToken,
  );
}

export async function deleteConversation(
  conversationID: string,
  csrfToken: string,
): Promise<void> {
  return apiRequest<void>(
    `/api/v1/conversations/${encodeURIComponent(conversationID)}`,
    { method: "DELETE" },
    csrfToken,
  );
}

export async function postConversationStream(
  conversationID: string,
  input: {
    content: string;
    client_message_id: string;
    agent_name?: string;
  },
  csrfToken: string,
  onEvent: (event: ConversationStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${apiBase()}/api/v1/conversations/${encodeURIComponent(conversationID)}/messages/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
      signal,
      credentials: "include",
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as {
      error?: string;
      message?: string;
    };
    throw new Error(chatErrorMessage(payload.error, payload.message));
  }
  if (!response.body) {
    throw new Error("无法读取流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const raw = trimmed.slice(5).trim();
        if (!raw || raw === "[DONE]") continue;
        let event: ConversationStreamEvent;
        try {
          event = JSON.parse(raw) as ConversationStreamEvent;
        } catch {
          continue;
        }
        onEvent(event);
        if (event.type === "error") {
          throw new Error(event.message || "生成失败");
        }
        if (event.type === "done") {
          return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function cancelAgentRun(
  runID: string,
  csrfToken: string,
): Promise<{ run_id: string; status: string }> {
  return apiRequest<{ run_id: string; status: string }>(
    `/api/v1/agent-runs/${encodeURIComponent(runID)}`,
    { method: "DELETE" },
    csrfToken,
  );
}

function chatErrorMessage(code?: string, detail?: string): string {
  if (detail) return detail;
  switch (code) {
    case "conversation_not_found":
      return "会话不存在或已被删除";
    case "conversation_busy":
      return "当前会话正在生成回答";
    case "duplicate_message":
      return "这条消息已经发送过了";
    case "invalid_conversation_input":
      return "会话内容不符合要求";
    case "authentication_required":
      return "登录状态已失效，请重新登录";
    case "csrf_validation_failed":
    case "invalid_csrf_token":
      return "页面凭据已失效，请刷新后重试";
    default:
      return "会话请求失败，请稍后重试";
  }
}
