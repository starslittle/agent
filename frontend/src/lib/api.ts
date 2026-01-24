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

// SSE 流式输出函数
export async function postQueryStreamSSE(
  payload: QueryPayload,
  onDelta: (delta: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const base = getApiBase();
  
  const res = await fetch(`${base}/query_stream_sse`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "Accept": "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal,
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

      // 🔥 改为逐行解析：不再强依赖 \n\n
      const lines = buffer.split("\n");
      
      // 保留最后一行（可能不完整）
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        // 忽略空行、注释、event: 行
        if (!trimmed || trimmed.startsWith(":") || trimmed.startsWith("event:")) continue;

        if (trimmed.startsWith("data: ")) {
          const jsonStr = trimmed.slice(6); // 去掉 "data: "
          
          if (jsonStr === "[DONE]") return;

          try {
            const data: StreamChunk = JSON.parse(jsonStr);
            
            if (data.type === "delta" && data.data) {
              onDelta(data.data);
            } else if (data.type === "error") {
              console.error("[API] 服务器错误:", data.message);
            } else if (data.type === "done") {
              return;
            }
          } catch (e) {
            // 跳过不完整的JSON（极少见）
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// 基于 LangGraph 的流式输出函数
export async function postQueryStreamGraph(
  payload: QueryPayload,
  onDelta: (delta: string, isThinking?: boolean, thinkingFinished?: boolean) => void,
  signal?: AbortSignal
): Promise<void> {
  const base = getApiBase();
  
  const res = await fetch(`${base}/query_stream_graph`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "Accept": "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal,
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

          try {
            const data: StreamChunk = JSON.parse(jsonStr);
            if (data.type === "delta" && data.data) {
              onDelta(data.data, data.isThinking, data.thinkingFinished);
            } else if (data.type === "done") {
              return;
            }
          } catch (e) {
            // ignore
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}


