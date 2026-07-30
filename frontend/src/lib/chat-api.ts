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

export type RuntimeActivityKind = "route" | "progress" | "model" | "tool";

export type RuntimeActivityStatus =
  | "started"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface RuntimeActivity {
  id: string;
  sequence?: number;
  kind: RuntimeActivityKind;
  status: RuntimeActivityStatus;
  label: string;
  name?: string;
  duration_ms?: number;
}

export interface RuntimeArtifact {
  artifact_id: string;
  artifact_type: string;
  content_hash: string;
  mime_type: string;
  size_bytes: number;
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
      type: "activity";
      sequence?: number;
      activity: RuntimeActivity;
    }
  | {
      type: "answer_delta";
      sequence?: number;
      data: string;
    }
  | {
      /**
       * @deprecated Migration-only compatibility for the legacy Python stream.
       * V1 must use activity/answer_delta instead.
       */
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
    }
  | {
      type: "artifact";
      sequence?: number;
      artifact: RuntimeArtifact;
    };

const runtimeActivityKinds = new Set<RuntimeActivityKind>([
  "route",
  "progress",
  "model",
  "tool",
]);

const runtimeActivityStatuses = new Set<RuntimeActivityStatus>([
  "started",
  "running",
  "completed",
  "failed",
  "cancelled",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOptionalNumber(
  value: Record<string, unknown>,
  key: string,
): boolean {
  return value[key] === undefined || typeof value[key] === "number";
}

function hasOptionalString(
  value: Record<string, unknown>,
  key: string,
): boolean {
  return value[key] === undefined || typeof value[key] === "string";
}

function hasOptionalBoolean(
  value: Record<string, unknown>,
  key: string,
): boolean {
  return value[key] === undefined || typeof value[key] === "boolean";
}

export function parseConversationStreamEvent(
  raw: string,
): ConversationStreamEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value) || typeof value.type !== "string") {
    return null;
  }

  switch (value.type) {
    case "meta":
      if (
        typeof value.conversation_id !== "string" ||
        typeof value.user_message_id !== "string" ||
        typeof value.assistant_message_id !== "string" ||
        typeof value.run_id !== "string" ||
        typeof value.title !== "string" ||
        !hasOptionalString(value, "execution_id") ||
        !hasOptionalNumber(value, "protocol_version")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "activity": {
      if (
        !hasOptionalNumber(value, "sequence") ||
        !isRecord(value.activity) ||
        typeof value.activity.id !== "string" ||
        typeof value.activity.label !== "string" ||
        !runtimeActivityKinds.has(value.activity.kind as RuntimeActivityKind) ||
        !runtimeActivityStatuses.has(
          value.activity.status as RuntimeActivityStatus,
        ) ||
        !hasOptionalNumber(value.activity, "sequence") ||
        !hasOptionalString(value.activity, "name") ||
        !hasOptionalNumber(value.activity, "duration_ms")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    }
    case "answer_delta":
      if (
        typeof value.data !== "string" ||
        !hasOptionalNumber(value, "sequence")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "artifact":
      if (
        !hasOptionalNumber(value, "sequence") ||
        !isRecord(value.artifact) ||
        typeof value.artifact.artifact_id !== "string" ||
        typeof value.artifact.artifact_type !== "string" ||
        typeof value.artifact.content_hash !== "string" ||
        typeof value.artifact.mime_type !== "string" ||
        typeof value.artifact.size_bytes !== "number"
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "delta":
      if (
        !hasOptionalString(value, "data") ||
        !hasOptionalBoolean(value, "isThinking") ||
        !hasOptionalBoolean(value, "thinkingFinished")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "done":
      if (
        !hasOptionalString(value, "message_id") ||
        !hasOptionalString(value, "status")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "error":
      if (!hasOptionalString(value, "message")) {
        return null;
      }
      return value as ConversationStreamEvent;
    default:
      return null;
  }
}

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
        const event = parseConversationStreamEvent(raw);
        if (!event) continue;
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
