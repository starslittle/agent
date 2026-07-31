import { Link } from "react-router-dom";
import { ChevronRight, LoaderCircle, RefreshCw } from "lucide-react";

import type { RunStatus, RunSummary } from "@/lib/run-api";
import { cn } from "@/lib/utils";
import { getVisibleSkill } from "@/features/skills/skills";
import { RunStatusBadge } from "./RunStatusBadge";
import { formatDuration, formatRunTime, RUN_FILTERS } from "./run-presentation";

interface RunListProps {
  items: RunSummary[];
  selectedRunID?: string;
  status: RunStatus | "";
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  error: string;
  onStatusChange: (status: RunStatus | "") => void;
  onRetry: () => void;
  onLoadMore: () => void;
}

export function RunList({
  items,
  selectedRunID,
  status,
  loading,
  loadingMore,
  hasMore,
  error,
  onStatusChange,
  onRetry,
  onLoadMore,
}: RunListProps) {
  return (
    <section className="flex h-full min-h-0 flex-col border-r border-border bg-card" aria-label="运行列表">
      <div className="border-b border-border p-4">
        <label htmlFor="run-status-filter" className="text-[11px] font-medium text-muted-foreground">状态筛选</label>
        <select
          id="run-status-filter"
          name="run-status"
          value={status}
          onChange={(event) => onStatusChange(event.target.value as RunStatus | "")}
          className="mt-2 h-11 w-full rounded-xl border border-input bg-background px-3 text-sm text-foreground outline-none focus:border-primary focus:ring-4 focus:ring-ring/15"
        >
          {RUN_FILTERS.map((filter) => <option key={filter.value || "all"} value={filter.value}>{filter.label}</option>)}
        </select>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex min-h-48 items-center justify-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            正在读取运行记录
          </div>
        ) : error ? (
          <div className="m-2 rounded-xl border border-destructive/25 bg-destructive/5 p-4">
            <p className="text-xs font-medium text-destructive">运行列表暂时无法加载</p>
            <p className="mt-1 break-words text-[11px] leading-5 text-muted-foreground">{error}</p>
            <button type="button" onClick={onRetry} className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl border border-border bg-background px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />重试
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex min-h-56 flex-col items-center justify-center px-5 text-center">
            <p className="text-sm font-medium">还没有符合条件的 Run</p>
            <p className="mt-2 max-w-xs text-xs leading-5 text-muted-foreground">从对话发起一次任务后，运行过程会出现在这里。</p>
            <Link to="/" className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-primary px-4 text-xs font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25">开始对话</Link>
          </div>
        ) : (
          <div className="space-y-1">
            {items.map((run) => {
              const skill = getVisibleSkill(run.primary_skill);
              const selected = run.id === selectedRunID;
              return (
                <Link
                  key={run.id}
                  to={`/agent-runs/${encodeURIComponent(run.id)}${status ? `?status=${status}` : ""}`}
                  className={cn(
                    "group block rounded-xl border px-3 py-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected ? "border-primary/35 bg-primary/5" : "border-transparent hover:border-border hover:bg-muted/50",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <RunStatusBadge status={run.status} />
                    <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 motion-reduce:transform-none" aria-hidden="true" />
                  </div>
                  <p className="mt-3 truncate font-mono text-[11px] text-foreground">{run.id}</p>
                  <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
                    <span className="truncate">{skill?.label ?? (run.primary_skill || "直接回答")}</span>
                    <span className="shrink-0">{formatDuration(run.total_duration_ms)}</span>
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground">{formatRunTime(run.started_at)}</p>
                </Link>
              );
            })}
          </div>
        )}

        {!loading && !error && hasMore && (
          <button type="button" onClick={onLoadMore} disabled={loadingMore} className="mt-2 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
            {loadingMore && <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            {loadingMore ? "正在加载" : "加载更多"}
          </button>
        )}
      </div>
    </section>
  );
}
