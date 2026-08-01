import type { RunEvent, RunStatus } from "@/lib/run-api";

export interface RunStatusPresentation {
  label: string;
  tone: "neutral" | "active" | "success" | "danger" | "warning";
}

export const RUN_STATUS: Record<RunStatus, RunStatusPresentation> = {
  queued: { label: "等待中", tone: "neutral" },
  running: { label: "运行中", tone: "active" },
  cancel_requested: { label: "正在取消", tone: "warning" },
  completed: { label: "已完成", tone: "success" },
  cancelled: { label: "已取消", tone: "neutral" },
  failed: { label: "失败", tone: "danger" },
  timed_out: { label: "超时", tone: "warning" },
};

export const RUN_FILTERS: Array<{ value: RunStatus | ""; label: string }> = [
  { value: "", label: "全部状态" },
  { value: "queued", label: "等待中" },
  { value: "running", label: "运行中" },
  { value: "cancel_requested", label: "正在取消" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
  { value: "failed", label: "失败" },
  { value: "timed_out", label: "超时" },
];

const EVENT_LABELS: Record<string, string> = {
  "run.created": "已创建运行",
  "run.started": "开始处理",
  "run.resolved": "已确定 Skill 与模型",
  "route.selected": "已选择执行路线",
  progress: "正在推进任务",
  "model.started": "开始生成回答",
  "model.completed": "回答生成完成",
  "model.failed": "回答生成失败",
  "tool.started": "开始调用工具",
  "tool.completed": "工具调用完成",
  "tool.failed": "工具调用失败",
  "tool.cancelled": "工具调用已取消",
  "citation.created": "记录引用来源",
  "artifact.created": "生成运行产物",
  usage: "已记录用量",
  "confirmation.required": "等待确认 Skill",
  "run.completed": "运行完成",
  "run.cancelled": "运行取消",
  "run.failed": "运行失败",
  "run.timed_out": "运行超时",
};

export function eventLabel(event: RunEvent): string {
  return EVENT_LABELS[event.type] ?? "运行事件";
}

export function stableRunEvents(events: RunEvent[]): RunEvent[] {
  return [...events].sort(
    (left, right) =>
      left.sequence - right.sequence ||
      left.occurred_at.localeCompare(right.occurred_at) ||
      left.type.localeCompare(right.type),
  );
}

export function formatDuration(durationMS?: number | null): string {
  if (durationMS === null || durationMS === undefined || durationMS < 0) return "—";
  if (durationMS < 1000) return `${durationMS}ms`;
  if (durationMS < 60_000) return `${(durationMS / 1000).toFixed(1)}s`;
  const minutes = Math.floor(durationMS / 60_000);
  const seconds = Math.round((durationMS % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatRunTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

interface SafeCitation {
  id: string;
  title: string;
  url: string;
  snippet: string;
}

interface SafeArtifact {
  id: string;
  type: string;
  mediaType: string;
  sizeBytes?: number;
}

function stringField(data: Record<string, unknown>, key: string): string {
  return typeof data[key] === "string" ? (data[key] as string).trim() : "";
}

export function safeCitation(event: RunEvent): SafeCitation | null {
  if (event.type !== "citation.created") return null;
  const id = stringField(event.data, "citation_id");
  const title = stringField(event.data, "title").slice(0, 300);
  const url = stringField(event.data, "url");
  const snippet = stringField(event.data, "snippet").slice(0, 500);
  if (!id || !title || !/^https?:\/\//i.test(url)) return null;
  return { id, title, url, snippet };
}

export function safeArtifact(event: RunEvent): SafeArtifact | null {
  if (event.type !== "artifact.created") return null;
  const id = stringField(event.data, "artifact_id");
  const type = stringField(event.data, "artifact_type");
  const mediaType = stringField(event.data, "media_type");
  const sizeBytes = typeof event.data.size_bytes === "number" ? event.data.size_bytes : undefined;
  if (!id || !type) return null;
  return { id, type, mediaType, sizeBytes };
}
