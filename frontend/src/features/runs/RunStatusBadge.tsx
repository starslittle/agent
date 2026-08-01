import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/run-api";
import { RUN_STATUS } from "./run-presentation";

const toneClasses = {
  neutral: "bg-muted text-muted-foreground",
  active: "bg-primary/10 text-primary",
  success: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  danger: "bg-destructive/10 text-destructive",
  warning: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const presentation = RUN_STATUS[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium", toneClasses[presentation.tone])}>
      {(status === "running" || status === "cancel_requested") && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" aria-hidden="true" />
      )}
      {presentation.label}
    </span>
  );
}
