export interface PublicSkillCapability {
  label: string;
  description: string;
}

export interface PublicSkillContextScope {
  label: string;
}

export interface PublicSkill {
  id: string;
  version: number;
  title: string;
  description: string;
  command: string;
  public_purpose: string;
  public_capabilities: PublicSkillCapability[];
  context_scope: PublicSkillContextScope[];
  confirmation_summary: string;
  may_propose_updates: boolean;
  available: boolean;
  effective: boolean;
}

function baseURL(): string {
  const env = (import.meta as unknown as { env?: Record<string, unknown> }).env || {};
  const base = env.VITE_API_BASE as string | undefined;
  return base ? base.replace(/\/$/, "") : "";
}

async function skillRequest<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${baseURL()}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { error?: string };
    if (payload.error === "skill_not_available") throw new Error("这个 Skill 当前不可用。");
    throw new Error("暂时无法读取可用 Skills。请检查网络后重试。");
  }
  return response.json() as Promise<T>;
}

export function listSkills(signal?: AbortSignal): Promise<{ items: PublicSkill[] }> {
  return skillRequest("/api/v1/skills", signal);
}

export function getSkill(skillID: string, signal?: AbortSignal): Promise<PublicSkill> {
  return skillRequest(`/api/v1/skills/${encodeURIComponent(skillID)}`, signal);
}
