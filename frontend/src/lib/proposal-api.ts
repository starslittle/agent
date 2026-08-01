export type ProposalStatus = "pending" | "accepted" | "rejected" | "deferred" | "superseded";
export type ProposalAction = "accept" | "reject" | "defer";
export type ProposalItemType = "confirmed_fact" | "current_state" | "personal_rule" | "ai_analysis";

export interface WikiProposal {
  id: string;
  target_item_id?: string | null;
  target_revision_id?: string | null;
  operation: "create" | "update";
  item_type: ProposalItemType;
  domain: string;
  proposed_content: string;
  source_type: string;
  source_reference?: string | null;
  source_detail?: string | null;
  document_id?: string | null;
  document_revision_id?: string | null;
  status: ProposalStatus;
  final_content?: string | null;
  resolution_action?: ProposalAction | null;
  resolved_at?: string | null;
  applied_item_id?: string | null;
  applied_revision_id?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ProposalResolution {
  proposal: WikiProposal;
  applied_item_id?: string | null;
  applied_revision_id?: string | null;
  replayed: boolean;
}

export interface ProposalTarget {
  item: { id: string; content: string; current_revision_id: string; version: number };
  revision: { id: string; content: string };
}

export interface ProposalDetail {
  proposal: WikiProposal;
  target?: ProposalTarget | null;
}

export class ProposalAPIError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "ProposalAPIError";
  }
}

function baseURL(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const base = env.VITE_API_BASE as string | undefined;
  return base ? base.replace(/\/$/, "") : "";
}

const messages: Record<string, string> = {
  wiki_proposal_not_found: "这条候选已不存在，或你没有访问权限。请刷新列表。",
  wiki_proposal_target_conflict: "原上下文已发生变化。请刷新并重新比较后再决定。",
  wiki_proposal_invalid_state: "这条候选已被处理。请刷新查看最新状态。",
  wiki_proposal_idempotency_conflict: "相同操作已经提交了不同内容。请刷新后重试。",
  invalid_wiki_proposal_input: "候选内容不符合要求，请检查编辑内容。",
  invalid_proposal_query: "候选筛选条件无效，请刷新页面。",
};

async function proposalRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseURL()}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: string };
    const code = payload.error || "proposal_request_failed";
    throw new ProposalAPIError(code, messages[code] || "候选操作没有完成。请检查网络后重试。");
  }
  return response.json() as Promise<T>;
}

export function listProposals(
  query: { documentID?: string; runID?: string; statuses?: ProposalStatus[]; limit?: number } = {},
  signal?: AbortSignal,
): Promise<{ items: WikiProposal[]; has_more: boolean }> {
  const params = new URLSearchParams({ limit: String(query.limit ?? 100) });
  if (query.documentID) params.set("document_id", query.documentID);
  if (query.runID) params.set("run_id", query.runID);
  if (query.statuses?.length) params.set("status", query.statuses.join(","));
  return proposalRequest(`/api/v1/wiki-proposals?${params}`, { signal });
}

export function getProposal(proposalID: string, signal?: AbortSignal): Promise<ProposalDetail> {
  return proposalRequest(`/api/v1/wiki-proposals/${encodeURIComponent(proposalID)}`, { signal });
}

export function resolveProposal(
  csrfToken: string,
  proposalID: string,
  action: ProposalAction,
  finalContent: string | null,
  idempotencyKey: string,
): Promise<ProposalResolution> {
  return proposalRequest(`/api/v1/wiki-proposals/${encodeURIComponent(proposalID)}/${action}`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken, "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(finalContent === null ? {} : { final_content: finalContent }),
  });
}
