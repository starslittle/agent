export interface QueryPayload {
  query: string;
  agent_name?: string | null;
  chat_history?: Array<{role: string; content: string}> | null;
}

export interface QueryResponse {
  agent_name: string;
  answer: string;
  output?: string | null;
}

function getApiBase(): string {
  // 开发期默认走 Vite 代理或直接本地后端；生产期相对路径同域
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
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

export interface StreamChunk {
  type: "delta" | "done" | "error";
  data?: string;
  message?: string;
}

export async function postQueryStream(
  payload: QueryPayload,
  onDelta: (delta: string) => void,
  signal?: AbortSignal
): Promise<void> {
  console.log("开始流式请求:", payload);
  const base = getApiBase();
  
  const res = await fetch(`${base}/query_stream`, {
    method: "POST",
    headers: { 
      "Content-Type": "application/json",
      "Accept": "application/x-ndjson"
    },
    body: JSON.stringify(payload),
    signal,
  });

  console.log("流式响应状态:", res.status);
  console.log("流式响应头:", [...res.headers.entries()]);

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`流式请求失败(${res.status}): ${txt || res.statusText}`);
  }

  const body = res.body;
  if (!body) {
    throw new Error("无法获取响应流");
  }
  const reader = body.getReader();

  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let chunkCount = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        console.log("流式读取完成，总块数:", chunkCount);
        break;
      }

      const text = decoder.decode(value, { stream: true });
      buffer += text;
      // 控制台打印可能导致性能问题，保留但可注释
      // console.log("收到原始数据:", text);
      
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // 保留最后一个不完整的行

      for (const line of lines) {
        if (!line.trim()) continue;
        
        chunkCount++;
        console.log(`处理第${chunkCount}行:`, line);
        
        try {
          const chunk: StreamChunk = JSON.parse(line);
          // console.log("解析结果:", chunk);
          
          if (chunk.type === "delta" && chunk.data) {
            // console.log("调用onDelta:", chunk.data);
            onDelta(chunk.data);
          } else if (chunk.type === "error") {
            throw new Error(chunk.message || "流式处理出错");
          } else if (chunk.type === "done") {
            // console.log("收到完成信号");
            return; // 正常结束
          }
        } catch (parseError) {
          console.warn("解析流式响应失败:", line, parseError);
          // 不抛出错误，继续处理其他行
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}


