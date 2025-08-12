export interface QueryPayload {
  query: string;
  agent_name?: string | null;
}

export interface QueryResponse {
  agent_name: string;
  answer: string;
  output?: string | null;
}

function getApiBase(): string {
  // 开发期默认走 Vite 代理或直接本地后端；生产期相对路径同域
  const env = (import.meta as any).env || {};
  const fromEnv = env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  return ""; // 相对路径
}

export async function postQuery(payload: QueryPayload, signal?: AbortSignal): Promise<QueryResponse> {
  const base = getApiBase();
  const res = await fetch(`${base}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`请求失败(${res.status}): ${txt || res.statusText}`);
  }
  return res.json();
}


