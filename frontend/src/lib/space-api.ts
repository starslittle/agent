export type SpaceSort = "name" | "recent";
export type SpaceEntryKind = "folder" | "document";

export interface SpaceEntry {
  id: string;
  parent_id?: string | null;
  kind: SpaceEntryKind;
  name: string;
  version: number;
  last_opened_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SpaceFolder extends SpaceEntry {
  kind: "folder";
}

export interface MarkdownDocument extends SpaceEntry {
  kind: "document";
  current_revision_id: string;
  revision_number: number;
  content: string;
  content_hash: string;
  size_bytes: number;
  source: "manual" | "import";
  original_relative_path?: string | null;
  media_type: "text/markdown";
  extraction_status: string;
  revision_created_at: string;
}

export interface DocumentRevision {
  id: string;
  document_id: string;
  revision_number: number;
  content: string;
  content_hash: string;
  size_bytes: number;
  source: "manual" | "import";
  original_relative_path?: string | null;
  media_type: string;
  created_by: string;
  created_at: string;
}

export interface SpaceListResponse {
  items: SpaceEntry[];
  limit: number;
  offset: number;
  has_more: boolean;
}

export type ImportItemStatus = "added" | "skipped_duplicate" | "conflict" | "unsupported" | "failed";

export interface MarkdownImportEntry {
  kind: "file" | "unsupported";
  relative_path: string;
  size: number;
  content_hash: string;
  media_type?: string;
  upload_field?: string;
}

export interface MarkdownImportManifest {
  batch_id: string;
  target_folder_id: string | null;
  root_name?: string | null;
  entries: MarkdownImportEntry[];
}

export interface MarkdownImportItem {
  relative_path: string;
  status: ImportItemStatus;
  reason?: string;
  entry_id?: string;
}

export interface MarkdownImportPreview {
  batch_id: string;
  target_folder_id: string | null;
  root_name?: string | null;
  markdown_count: number;
  total_bytes: number;
  unsupported: number;
  duplicates: number;
  conflicts: number;
  items: MarkdownImportItem[];
}

export interface MarkdownImportResult {
  batch_id: string;
  root_folder_id?: string;
  items: MarkdownImportItem[];
  added: number;
  duplicates: number;
  conflicts: number;
  unsupported: number;
  failed: number;
  replayed: boolean;
}

export class SpaceAPIError extends Error {
  constructor(public readonly code: string, public readonly status: number) {
    super(spaceErrorMessage(code));
  }
}

function configuredBase(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const base = env.VITE_API_BASE as string | undefined;
  return base ? base.replace(/\/$/, "") : "";
}

async function spaceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${configuredBase()}${path}`, {
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
    throw new SpaceAPIError(payload.error || "space_request_failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function mutation(method: string, csrfToken: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "X-CSRF-Token": csrfToken },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
}

export function listSpaceEntries(parentID: string | null, sort: SpaceSort, offset = 0, signal?: AbortSignal, limit = 48): Promise<SpaceListResponse> {
  const query = new URLSearchParams({ sort, limit: String(limit), offset: String(offset) });
  if (parentID) query.set("parent_id", parentID);
  return spaceRequest<SpaceListResponse>(`/api/v1/space/entries?${query}`, { signal });
}

export function getFolder(folderID: string, signal?: AbortSignal): Promise<SpaceFolder> {
  return spaceRequest<SpaceFolder>(`/api/v1/space/folders/${encodeURIComponent(folderID)}`, { signal });
}

export function getFolderBreadcrumbs(folderID: string, signal?: AbortSignal): Promise<{ items: SpaceFolder[] }> {
  return spaceRequest<{ items: SpaceFolder[] }>(`/api/v1/space/folders/${encodeURIComponent(folderID)}/breadcrumbs`, { signal });
}

export function createFolder(csrfToken: string, input: { parent_id: string | null; name: string }): Promise<SpaceFolder> {
  return spaceRequest<SpaceFolder>("/api/v1/space/folders", createMutation(csrfToken, input));
}

export function updateFolder(csrfToken: string, folderID: string, input: { parent_id: string | null; name: string; expected_version: number }): Promise<SpaceFolder> {
  return spaceRequest<SpaceFolder>(`/api/v1/space/folders/${encodeURIComponent(folderID)}`, mutation("PATCH", csrfToken, input));
}

export function deleteFolder(csrfToken: string, folder: SpaceFolder): Promise<void> {
  return spaceRequest<void>(`/api/v1/space/folders/${encodeURIComponent(folder.id)}`, mutation("DELETE", csrfToken, { expected_version: folder.version, confirm_name: folder.name }));
}

export function createDocument(csrfToken: string, input: { folder_id: string; name: string; content: string }): Promise<MarkdownDocument> {
  return spaceRequest<MarkdownDocument>("/api/v1/space/documents", createMutation(csrfToken, { ...input, source: "manual" }));
}

export function getDocument(documentID: string, signal?: AbortSignal): Promise<MarkdownDocument> {
  return spaceRequest<MarkdownDocument>(`/api/v1/space/documents/${encodeURIComponent(documentID)}`, { signal });
}

export function updateDocument(csrfToken: string, documentID: string, content: string, expectedVersion: number): Promise<MarkdownDocument> {
  return spaceRequest<MarkdownDocument>(`/api/v1/space/documents/${encodeURIComponent(documentID)}`, mutation("PATCH", csrfToken, { content, expected_version: expectedVersion }));
}

export function moveDocument(csrfToken: string, documentID: string, input: { parent_id: string; name: string; expected_version: number }): Promise<MarkdownDocument> {
  return spaceRequest<MarkdownDocument>(`/api/v1/space/documents/${encodeURIComponent(documentID)}/location`, mutation("PATCH", csrfToken, input));
}

export function deleteDocument(csrfToken: string, document: MarkdownDocument): Promise<void> {
  return spaceRequest<void>(`/api/v1/space/documents/${encodeURIComponent(document.id)}`, mutation("DELETE", csrfToken, { expected_version: document.version, confirm_name: document.name }));
}

export function listDocumentRevisions(documentID: string, signal?: AbortSignal): Promise<{ items: DocumentRevision[] }> {
  return spaceRequest<{ items: DocumentRevision[] }>(`/api/v1/space/documents/${encodeURIComponent(documentID)}/revisions?limit=50`, { signal });
}

export function preflightMarkdownImport(csrfToken: string, manifest: MarkdownImportManifest, signal?: AbortSignal): Promise<MarkdownImportPreview> {
  return spaceRequest<MarkdownImportPreview>("/api/v1/space/imports:preflight", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(manifest),
    signal,
  });
}

export function uploadMarkdownImport(
  csrfToken: string,
  idempotencyKey: string,
  manifest: MarkdownImportManifest,
  files: Map<string, File>,
  onProgress: (percent: number) => void,
  signal: AbortSignal,
): Promise<MarkdownImportResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("manifest", JSON.stringify(manifest));
    for (const entry of manifest.entries) {
      if (entry.kind === "file" && entry.upload_field) {
        const file = files.get(entry.upload_field);
        if (file) form.append(entry.upload_field, file, entry.relative_path.split("/").at(-1));
      }
    }
    xhr.open("POST", `${configuredBase()}/api/v1/space/imports`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.setRequestHeader("Idempotency-Key", idempotencyKey);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onload = () => {
      let payload: MarkdownImportResult & { error?: string };
      try {
        payload = JSON.parse(xhr.responseText || "{}") as MarkdownImportResult & { error?: string };
      } catch {
        reject(new Error("服务返回了无法识别的导入结果"));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
      else reject(new SpaceAPIError(payload.error || "space_request_failed", xhr.status));
    };
    xhr.onerror = () => reject(new Error("上传连接中断，请重试"));
    xhr.onabort = () => reject(new DOMException("导入已取消", "AbortError"));
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onloadend = () => signal.removeEventListener("abort", abort);
    xhr.send(form);
  });
}

function spaceErrorMessage(code: string): string {
  switch (code) {
    case "space_entry_not_found": return "这个项目不存在，或你没有访问权限";
    case "space_name_conflict": return "当前文件夹中已经有同名项目";
    case "space_version_conflict": return "内容已在别处更新，请刷新后再试";
    case "folder_not_empty": return "请先移走或删除文件夹中的内容";
    case "space_limit_exceeded": return "内容超出当前空间限制";
    case "confirmation_name_mismatch": return "确认名称不匹配";
    case "invalid_space_input": return "名称、路径或内容不符合要求";
    case "import_idempotency_conflict": return "这次导入请求已被其他内容使用，请重新选择文件";
    default: return "空间操作没有完成，请稍后重试";
  }
}

function createMutation(csrfToken: string, body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken, "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(body),
  };
}
