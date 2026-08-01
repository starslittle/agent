export type ExtractionRunStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "completed"
  | "cancelled"
  | "failed"
  | "timed_out";

export interface DocumentExtractionRun {
  run_id: string;
  execution_id: string;
  conversation_id: string;
  status: ExtractionRunStatus;
  run_purpose: "document_extraction";
  document_id: string;
  document_revision_id: string;
  events_url: string;
  replayed: boolean;
}

export interface DocumentProposal {
  id: string;
  target_item_id?: string | null;
  target_revision_id?: string | null;
  operation: "create" | "update";
  item_type: "confirmed_fact" | "current_state" | "personal_rule" | "ai_analysis";
  domain: string;
  proposed_content: string;
  source_reference?: string | null;
  source_detail?: string | null;
  document_id: string;
  document_revision_id: string;
  status: "pending" | "accepted" | "rejected" | "deferred" | "superseded";
  created_at: string;
}

const DOCUMENT_EXTRACTION_VERSION = "document-extraction-v1";

export function documentExtractionIdempotencyKey(
  documentRevisionID: string,
  retryNonce?: string,
): string {
  const base = `document-extraction:${documentRevisionID}:${DOCUMENT_EXTRACTION_VERSION}`;
  return retryNonce ? `${base}:retry:${retryNonce}` : base;
}

function baseURL(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const base = env.VITE_API_BASE as string | undefined;
  return base ? base.replace(/\/$/, "") : "";
}

async function documentRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseURL()}${path}`, {
    credentials: "include",
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: string };
    const messages: Record<string, string> = {
      document_not_found: "这篇文档不存在，或你没有访问权限",
      document_extraction_limit_exceeded: "当前文档过长，暂时无法进行结构化提取",
      document_extraction_active: "这篇文档已有一次提取正在运行",
      document_extraction_scheduler_unavailable: "提取服务暂时不可用，请稍后重试",
    };
    throw new Error(messages[payload.error || ""] || "文档提取没有启动，请稍后重试");
  }
  return response.json() as Promise<T>;
}

export function startDocumentExtraction(
  csrfToken: string,
  documentID: string,
  idempotencyKey: string,
): Promise<DocumentExtractionRun> {
  return documentRequest<DocumentExtractionRun>(
    `/api/v1/space/documents/${encodeURIComponent(documentID)}/extractions`,
    {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
      },
    },
  );
}

export function listDocumentProposals(
  documentID: string,
  signal?: AbortSignal,
): Promise<{ items: DocumentProposal[] }> {
  const query = new URLSearchParams({
    document_id: documentID,
    status: "pending,deferred",
    limit: "100",
  });
  return documentRequest<{ items: DocumentProposal[] }>(
    `/api/v1/wiki-proposals?${query}`,
    { signal },
  );
}
