import React from "react";
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  Circle,
  LoaderCircle,
  XCircle,
} from "lucide-react";

import type {
  RuntimeActivity,
  RuntimeActivityStatus,
} from "@/lib/chat-api";
import type { RuntimeMessageStatus } from "@/lib/conversation-stream-reducer";
import {
  buildRuntimeActivityView,
  type RuntimeActivityTone,
} from "./runtime-activity-view";

interface RuntimeActivityListProps {
  activities: RuntimeActivity[];
  messageStatus?: RuntimeMessageStatus;
}

const statusLabels: Record<RuntimeActivityStatus, string> = {
  started: "已开始",
  running: "进行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const durationFormatter = new Intl.NumberFormat("zh-CN");

export const RuntimeActivityList: React.FC<RuntimeActivityListProps> = ({
  activities,
  messageStatus,
}) => {
  const isStreaming = messageStatus === "streaming";
  const [expanded, setExpanded] = React.useState(false);
  const panelID = React.useId();

  React.useEffect(() => {
    if (!isStreaming) {
      setExpanded(false);
    }
  }, [isStreaming]);

  if (activities.length === 0) return null;

  const view = buildRuntimeActivityView(activities, messageStatus);
  const liveSummary = `${view.headline}，${view.detail}`;

  return (
    <section
      className="mb-4 w-full"
      aria-label="运行过程"
    >
      <button
        type="button"
        className="group flex min-h-11 w-full items-center justify-between gap-3 rounded-xl bg-muted/45 px-3.5 py-2 text-left transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={expanded}
        aria-controls={panelID}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="flex min-w-0 flex-1 items-center gap-2.5">
          <ActivityToneIcon tone={view.tone} />
          <span className="truncate text-sm font-medium text-foreground">
            {view.headline}
          </span>
          <span
            aria-hidden="true"
            className="hidden shrink-0 text-muted-foreground/60 sm:inline"
          >
            ·
          </span>
          <span className="hidden truncate text-xs font-normal text-muted-foreground sm:inline">
            {view.detail}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-muted-foreground group-hover:text-foreground">
          {expanded ? "收起" : "查看过程"}
          <ChevronDown
            aria-hidden="true"
            className={`h-4 w-4 transition-transform motion-reduce:transition-none ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </span>
      </button>

      <span className="sr-only" aria-live="polite">
        {liveSummary}
      </span>

      {expanded && (
        <ol
          id={panelID}
          className="ml-5 mt-2 space-y-3 border-l border-border/80 py-1 pl-5"
        >
          {view.milestones.map((activity) => (
            <li
              key={activity.id}
              className="relative flex min-w-0 items-start gap-2.5 text-xs"
            >
              <span className="absolute -left-[1.78rem] grid h-4 w-4 place-items-center bg-card">
                <ActivityStatusIcon status={activity.status} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block break-words leading-5 text-foreground">
                  {activity.label}
                  {activity.duration_ms !== undefined && (
                    <span className="text-muted-foreground">
                      {` · ${formatDuration(activity.duration_ms)}`}
                    </span>
                  )}
                </span>
                <span className="sr-only">
                  {statusLabels[activity.status]}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};

function ActivityToneIcon({ tone }: { tone: RuntimeActivityTone }) {
  if (tone === "running") {
    return (
      <LoaderCircle
        aria-hidden="true"
        className="h-4 w-4 shrink-0 animate-spin text-primary motion-reduce:animate-none"
      />
    );
  }
  if (tone === "completed") {
    return (
      <CheckCircle2
        aria-hidden="true"
        className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400"
      />
    );
  }
  if (tone === "failed") {
    return (
      <XCircle
        aria-hidden="true"
        className="h-4 w-4 shrink-0 text-destructive"
      />
    );
  }
  return (
    <Ban
      aria-hidden="true"
      className="h-4 w-4 shrink-0 text-muted-foreground"
    />
  );
}

function ActivityStatusIcon({
  status,
}: {
  status: RuntimeActivityStatus;
}) {
  const commonClassName = "mt-0.5 h-4 w-4 shrink-0";
  switch (status) {
    case "started":
    case "running":
      return (
        <LoaderCircle
          aria-hidden="true"
          className={`${commonClassName} animate-spin text-primary motion-reduce:animate-none`}
        />
      );
    case "completed":
      return (
        <CheckCircle2
          aria-hidden="true"
          className={`${commonClassName} text-emerald-600 dark:text-emerald-400`}
        />
      );
    case "failed":
      return (
        <XCircle
          aria-hidden="true"
          className={`${commonClassName} text-destructive`}
        />
      );
    case "cancelled":
      return (
        <Ban
          aria-hidden="true"
          className={`${commonClassName} text-muted-foreground`}
        />
      );
    default:
      return (
        <Circle
          aria-hidden="true"
          className={`${commonClassName} text-muted-foreground`}
        />
      );
  }
}

function formatDuration(durationMS: number): string {
  if (durationMS >= 1000) {
    return `${new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits: 1,
    }).format(durationMS / 1000)} 秒`;
  }
  return `${durationFormatter.format(durationMS)} ms`;
}
