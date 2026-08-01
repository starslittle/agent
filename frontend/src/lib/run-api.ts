export type RunStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "completed"
  | "cancelled"
  | "failed"
  | "timed_out";

export interface RunSummary {
  id: string;
  execution_id: string;
  trace_id: string;
  conversation_id: string;
  model_id: string;
  requested_skill?: string | null;
  resolved_skills: string[] | null;
  primary_skill?: string | null;
  selection_source?: string | null;
  context_package_id?: string | null;
  actual_route?: string | null;
  model_name?: string | null;
  status: RunStatus;
  protocol_version: number;
  service_version?: string | null;
  agent_version?: string | null;
  graph_version?: string | null;
  prompt_bundle_hash?: string | null;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  model_call_count: number;
  tool_call_count: number;
  retrieval_count: number;
  total_duration_ms?: number | null;
  error_code?: string | null;
  error_detail?: string | null;
  first_token_at?: string | null;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
  user_id?: string;
}

export interface RunEvent {
  sequence: number;
  type: string;
  occurred_at: string;
  trace_id: string;
  span_id?: string | null;
  parent_span_id?: string | null;
  category?: string | null;
  stage?: string | null;
  event_schema_version: number;
  content_capture_level: string;
  data: Record<string, unknown>;
}

export interface RunSpan {
  span_id: string;
  parent_span_id?: string | null;
  type: string;
  name: string;
  stage?: string | null;
  status: string;
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
  error_code?: string | null;
  attributes: Record<string, unknown>;
}

export interface RunDetail {
  run: RunSummary;
  spans: RunSpan[];
  events: RunEvent[];
  prompts: unknown[];
}

export interface RunListResponse {
  items: RunSummary[];
  next_before?: string | null;
}

export interface RunListQuery {
  status?: RunStatus | "";
  before?: string | null;
  limit?: number;
}

export interface ObservabilityRunListQuery extends RunListQuery {
  userID?: string;
  skill?: string;
  workflow?: string;
  model?: string;
  errorCode?: string;
  from?: string;
  to?: string;
}

async function runRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const configuredBase = env.VITE_API_BASE as string | undefined;
  const base = configuredBase ? configuredBase.replace(/\/$/, "") : "";
  const response = await fetch(`${base}${path}`, { credentials: "include", signal });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      error?: string;
      message?: string;
    };
    throw new Error(payload.message || payload.error || `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export function listRuns(
  query: RunListQuery = {},
  signal?: AbortSignal,
): Promise<RunListResponse> {
  const params = new URLSearchParams({ limit: String(query.limit ?? 20) });
  if (query.status) params.set("status", query.status);
  if (query.before) params.set("before", query.before);
  return runRequest<RunListResponse>(`/api/v1/agent-runs?${params}`, signal);
}

export function getRunDetail(runID: string, signal?: AbortSignal): Promise<RunDetail> {
  return runRequest<RunDetail>(
    `/api/v1/agent-runs/${encodeURIComponent(runID)}`,
    signal,
  );
}

export function listObservableRuns(
  query: ObservabilityRunListQuery = {},
  signal?: AbortSignal,
): Promise<RunListResponse> {
  const params = new URLSearchParams({ limit: String(query.limit ?? 20) });
  const filters: Array<[string, string | undefined | null]> = [
    ["user_id", query.userID],
    ["skill", query.skill],
    ["workflow", query.workflow],
    ["model", query.model],
    ["status", query.status],
    ["error_code", query.errorCode],
    ["from", query.from],
    ["to", query.to],
    ["before", query.before],
  ];
  filters.forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return runRequest<RunListResponse>(`/api/v1/internal/agent-runs?${params}`, signal);
}

export function getObservableRunDetail(
  runID: string,
  signal?: AbortSignal,
): Promise<RunDetail> {
  return runRequest<RunDetail>(
    `/api/v1/internal/agent-runs/${encodeURIComponent(runID)}`,
    signal,
  );
}
