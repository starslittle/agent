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
import {
  runtimeActivitySummary,
  type RuntimeMessageStatus,
} from "@/lib/conversation-stream-reducer";

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
  const [expanded, setExpanded] = React.useState(isStreaming);
  const panelID = React.useId();

  React.useEffect(() => {
    if (!isStreaming) {
      setExpanded(false);
    }
  }, [isStreaming]);

  if (activities.length === 0) return null;

  const summary = runtimeActivitySummary(activities, messageStatus);

  return (
    <section
      className="mb-4 overflow-hidden rounded-xl border border-border/70 bg-muted/35"
      aria-label="运行过程"
    >
      <button
        type="button"
        className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs font-medium text-foreground transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/40"
        aria-expanded={expanded}
        aria-controls={panelID}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="min-w-0 break-words">{summary}</span>
        <ChevronDown
          aria-hidden="true"
          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      <span className="sr-only" aria-live="polite">
        {summary}
      </span>

      {expanded && (
        <ol
          id={panelID}
          className="space-y-2 border-t border-border/60 px-3 py-3"
        >
          {activities.map((activity) => (
            <li
              key={activity.id}
              className="flex min-w-0 items-start gap-2.5 text-xs"
            >
              <ActivityStatusIcon status={activity.status} />
              <span className="min-w-0 flex-1">
                <span className="block break-words text-foreground">
                  {activity.label}
                </span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {statusLabels[activity.status]}
                  {activity.duration_ms !== undefined &&
                    ` · ${durationFormatter.format(activity.duration_ms)} ms`}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
};

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
