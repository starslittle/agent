export type WikiType = "confirmed_fact" | "current_state" | "personal_rule" | "ai_analysis";
export type WikiStatus = "candidate" | "confirmed" | "rejected" | "outdated" | "forgotten";

export interface WikiItem {
  id: string;
  type: WikiType;
  domain: string;
  status: WikiStatus;
  status_before_forgotten?: WikiStatus | null;
  current_revision_id: string;
  content: string;
  revision_number: number;
  confirmed_by_user: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WikiSource {
  id: string;
  item_id: string;
  revision_id: string;
  type: string;
  reference?: string | null;
  detail?: string | null;
  document_id?: string | null;
  document_revision_id?: string | null;
  created_at: string;
}

export interface WikiDetail {
  item: WikiItem;
  revision: { id: string; item_id: string; revision_number: number; content: string; created_by: string; replaces_revision_id?: string | null; created_at: string };
  sources: WikiSource[];
}

function baseURL(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const base = env.VITE_API_BASE as string | undefined;
  return base ? base.replace(/\/$/, "") : "";
}

async function wikiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseURL()}${path}`, {
    credentials: "include", ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: string };
    const code = payload.error || "wiki_request_failed";
    const messages: Record<string, string> = {
      wiki_item_not_found: "这条上下文不存在，或你没有访问权限",
      wiki_version_conflict: "这条上下文已更新，请刷新后再试",
      wiki_invalid_state: "当前状态不支持这个操作",
      invalid_wiki_input: "上下文内容不符合要求",
      confirmation_content_mismatch: "确认内容不匹配",
    };
    throw new Error(messages[code] || "上下文操作没有完成，请稍后重试");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function mutate(method: string, csrfToken: string, body: unknown): RequestInit {
  return { method, headers: { "X-CSRF-Token": csrfToken }, body: JSON.stringify(body) };
}

export function listWikiItems(documentID: string, includeForgotten = false, signal?: AbortSignal): Promise<{ items: WikiItem[] }> {
  const query = new URLSearchParams({ document_id: documentID, include_forgotten: String(includeForgotten), limit: "100" });
  return wikiRequest<{ items: WikiItem[] }>(`/api/v1/wiki-items?${query}`, { signal });
}

export function getWikiItem(itemID: string, signal?: AbortSignal): Promise<WikiDetail> {
  return wikiRequest<WikiDetail>(`/api/v1/wiki-items/${encodeURIComponent(itemID)}`, { signal });
}

export function createWikiItem(csrfToken: string, input: { type: WikiType; domain: string; content: string; document_id?: string; document_revision_id?: string }): Promise<WikiDetail> {
  return wikiRequest<WikiDetail>("/api/v1/wiki-items", {
    ...mutate("POST", csrfToken, { ...input, status: "confirmed", source_type: input.document_id ? "document_extracted" : "user_stated" }),
    headers: { "X-CSRF-Token": csrfToken, "Idempotency-Key": crypto.randomUUID() },
  });
}

export function updateWikiItem(csrfToken: string, item: WikiItem, content: string): Promise<WikiDetail> {
  return wikiRequest<WikiDetail>(`/api/v1/wiki-items/${encodeURIComponent(item.id)}`, mutate("PATCH", csrfToken, { content, expected_version: item.version }));
}

export function changeWikiStatus(csrfToken: string, item: WikiItem, action: "outdated" | "forget" | "restore"): Promise<WikiItem> {
  return wikiRequest<WikiItem>(`/api/v1/wiki-items/${encodeURIComponent(item.id)}/${action}`, mutate("POST", csrfToken, { expected_version: item.version }));
}

export function deleteWikiItem(csrfToken: string, item: WikiItem): Promise<void> {
  return wikiRequest<void>(`/api/v1/wiki-items/${encodeURIComponent(item.id)}`, mutate("DELETE", csrfToken, { expected_version: item.version, confirm_content: item.content }));
}
