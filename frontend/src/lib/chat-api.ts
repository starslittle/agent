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

export type CitationSourceType = "web" | "knowledge" | "tool";

export interface RuntimeCitation {
  citation_id: string;
  title: string;
  url: string;
  snippet: string;
  source_type: CitationSourceType;
  artifact_id: string;
  sequence: number;
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
      type: "confirmation_required";
      sequence?: number;
      suggested_skill: "research" | "fortune";
      confidence: number;
      reason_code: "automatic_confirmation_required";
    }
  | {
      type: "citation";
      sequence?: number;
      citation: RuntimeCitation;
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
      sequence?: number;
      message_id?: string;
      status?: string;
      error_code?: string;
    }
  | {
      type: "error";
      code?: string;
      message?: string;
      expected_sequence?: number;
      received_sequence?: number;
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

const citationSourceTypes = new Set<CitationSourceType>([
  "web",
  "knowledge",
  "tool",
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

export function parseRuntimeCitation(value: unknown): RuntimeCitation | null {
  if (
    !isRecord(value) ||
    typeof value.citation_id !== "string" ||
    value.citation_id.length === 0 ||
    value.citation_id.length > 128 ||
    typeof value.title !== "string" ||
    value.title.trim().length === 0 ||
    value.title.length > 300 ||
    typeof value.url !== "string" ||
    value.url.length > 500 ||
    typeof value.snippet !== "string" ||
    value.snippet.length > 500 ||
    typeof value.source_type !== "string" ||
    !citationSourceTypes.has(value.source_type as CitationSourceType) ||
    typeof value.artifact_id !== "string" ||
    value.artifact_id.length === 0 ||
    value.artifact_id.length > 200 ||
    typeof value.sequence !== "number" ||
    !Number.isInteger(value.sequence) ||
    value.sequence < 1
  ) {
    return null;
  }
  try {
    const parsed = new URL(value.url);
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      parsed.username ||
      parsed.password
    ) {
      return null;
    }
  } catch {
    return null;
  }
  return value as unknown as RuntimeCitation;
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
    case "confirmation_required":
      if (
        (value.suggested_skill !== "research" &&
          value.suggested_skill !== "fortune") ||
        typeof value.confidence !== "number" ||
        value.confidence < 0 ||
        value.confidence > 1 ||
        value.reason_code !== "automatic_confirmation_required" ||
        !hasOptionalNumber(value, "sequence")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "citation":
      if (
        !hasOptionalNumber(value, "sequence") ||
        parseRuntimeCitation(value.citation) === null
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
        !hasOptionalNumber(value, "sequence") ||
        !hasOptionalString(value, "message_id") ||
        !hasOptionalString(value, "status") ||
        !hasOptionalString(value, "error_code")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    case "error":
      if (
        !hasOptionalString(value, "code") ||
        !hasOptionalString(value, "message") ||
        !hasOptionalNumber(value, "expected_sequence") ||
        !hasOptionalNumber(value, "received_sequence")
      ) {
        return null;
      }
      return value as ConversationStreamEvent;
    default:
      return null;
  }
}

function apiBase(): string {
  const env =
    (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const value = env.VITE_API_BASE as string | undefined;
  return value ? value.replace(/\/$/, "") : "";
}

export class ChatAPIError extends Error {
  readonly code?: string;

  constructor(code?: string, detail?: string) {
    super(chatErrorMessage(code, detail));
    this.name = "ChatAPIError";
    this.code = code;
  }
}

export function isRunCreateNotEnabled(error: unknown): boolean {
  return (
    error instanceof ChatAPIError && error.code === "run_create_not_enabled"
  );
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
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new ChatAPIError(payload.error, payload.message);
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
): Promise<Conversation> {
  return apiRequest<Conversation>(
    "/api/v1/conversations",
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    csrfToken,
  );
}

export async function getConversation(id: string): Promise<Conversation> {
  return apiRequest<Conversation>(
    `/api/v1/conversations/${encodeURIComponent(id)}`,
  );
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

export interface CreateAgentRunResponse {
  run_id: string;
  execution_id: string;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  status: AgentRunStatus;
  protocol_version: number;
  model_id: string;
  requested_skill?: string | null;
  events_url: string;
}

export type AgentRunStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "completed"
  | "cancelled"
  | "failed"
  | "timed_out";

export interface AgentRunSummary {
  id: string;
  execution_id: string;
  conversation_id: string;
  status: AgentRunStatus;
  protocol_version: number;
  model_id: string;
  requested_skill?: string | null;
  resolved_skills: string[] | null;
  primary_skill?: string | null;
  selection_source?:
    | "direct"
    | "user"
    | "compatibility"
    | "automatic"
    | "fallback"
    | null;
  started_at: string;
}

export interface AgentRunDetail {
  run: AgentRunSummary;
  spans: Array<Record<string, unknown>>;
  events: Array<Record<string, unknown>>;
  prompts: Array<Record<string, unknown>>;
}

interface AgentRunListResponse {
  items: AgentRunSummary[];
  next_before?: string | null;
}

export async function createAgentRun(
  conversationID: string,
  input: {
    content: string;
    client_message_id: string;
    idempotency_key: string;
    model_id?: string;
    requested_skill?: string | null;
  },
  csrfToken: string,
): Promise<CreateAgentRunResponse> {
  return apiRequest<CreateAgentRunResponse>(
    `/api/v1/conversations/${encodeURIComponent(conversationID)}/runs`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
    csrfToken,
  );
}

export async function streamLegacyConversation(
  conversationID: string,
  input: {
    content: string;
    client_message_id: string;
    model_id?: string;
    requested_skill?: string | null;
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
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
      signal,
      credentials: "include",
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new ChatAPIError(payload.error, payload.message);
  }
  if (!response.body) throw new Error("无法读取流式响应");

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
        if (event.type === "error") {
          throw new Error(event.message || "服务器流式处理失败");
        }
        onEvent(event);
        if (event.type === "done") return;
      }
    }
    throw new Error("运行连接提前结束，请重试");
  } finally {
    reader.releaseLock();
  }
}

export async function listAgentRuns(
  limit = 100,
): Promise<AgentRunListResponse> {
  return apiRequest<AgentRunListResponse>(
    `/api/v1/agent-runs?limit=${encodeURIComponent(String(limit))}`,
  );
}

export async function getAgentRun(runID: string): Promise<AgentRunDetail> {
  return apiRequest<AgentRunDetail>(
    `/api/v1/agent-runs/${encodeURIComponent(runID)}`,
  );
}

export async function attachAgentRun(
  runID: string,
  startingAfter: number,
  onEvent: (event: ConversationStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${apiBase()}/api/v1/agent-runs/${encodeURIComponent(runID)}/events?starting_after=${encodeURIComponent(String(startingAfter))}`,
    {
      headers: {
        Accept: "text/event-stream",
      },
      signal,
      credentials: "include",
    },
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new ChatAPIError(payload.error, payload.message);
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
        if (event.type === "error") {
          throw new Error(attachErrorMessage(event.code, event.message));
        }
        onEvent(event);
        if (event.type === "done") {
          return;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function attachErrorMessage(code?: string, detail?: string): string {
  if (detail) return detail;
  if (code === "agent_event_sequence_gap") {
    return "运行事件暂时不连续，正在重新连接";
  }
  return "运行连接中断，正在重新连接";
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
    case "invalid_cursor":
      return "运行恢复位置无效，请刷新后重试";
    case "run_create_not_enabled":
      return "当前环境尚未启用运行服务";
    default:
      return "会话请求失败，请稍后重试";
  }
}
