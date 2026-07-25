export interface QueryPayload {
  query: string;
  agent_name?: string | null;
  chat_history?: Array<{role: string; content: string}> | null;
}

function getApiBase(): string {
  // 开发期默认走 Vite 代理或直接本地后端；生产期相对路径同域
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const fromEnv = env.VITE_API_BASE as string | undefined;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  return ""; // 相对路径
}

export interface StreamChunk {
  type: "delta" | "done" | "error";
  data?: string;
  message?: string;
  isThinking?: boolean;
  thinkingFinished?: boolean;
}

// 基于 LangGraph 的流式输出函数
export async function postQueryStreamGraph(
  payload: QueryPayload,
  onDelta: (delta: string, isThinking?: boolean, thinkingFinished?: boolean) => void,
  csrfToken: string,
  signal?: AbortSignal
): Promise<void> {
  const base = getApiBase();
  
  const res = await fetch(`${base}/query_stream`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
      "X-CSRF-Token": csrfToken,
    },
    body: JSON.stringify(payload),
    signal,
    credentials: "include",
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`SSE 请求失败(${res.status}): ${txt || res.statusText}`);
  }

  const body = res.body;
  if (!body) throw new Error("无法获取响应流");
  
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(":") || trimmed.startsWith("event:")) continue;

        if (trimmed.startsWith("data: ")) {
          const jsonStr = trimmed.slice(6);
          if (jsonStr === "[DONE]") return;

          let data: StreamChunk;
          try {
            data = JSON.parse(jsonStr) as StreamChunk;
          } catch {
            // 忽略不完整或非 JSON 的 SSE 数据行；业务错误不能在这里吞掉
            continue;
          }

          if (data.type === "delta" && data.data) {
            onDelta(data.data, data.isThinking, data.thinkingFinished);
          } else if (data.type === "error") {
            throw new Error(data.message || "服务器流式处理失败");
          } else if (data.type === "done") {
            return;
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

