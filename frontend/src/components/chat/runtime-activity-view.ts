import type {
  RuntimeActivity,
  RuntimeActivityStatus,
} from "@/lib/chat-api";
import type { RuntimeMessageStatus } from "@/lib/conversation-stream-reducer";

export type RuntimeActivityTone =
  | "running"
  | "completed"
  | "failed"
  | "stopped";

export interface RuntimeActivityView {
  headline: string;
  detail: string;
  tone: RuntimeActivityTone;
  milestones: RuntimeActivity[];
}

const terminalStatuses = new Set<RuntimeActivityStatus>([
  "completed",
  "failed",
  "cancelled",
]);

const MAX_VISIBLE_MILESTONES = 6;

export function buildRuntimeActivityView(
  activities: RuntimeActivity[],
  messageStatus?: RuntimeMessageStatus,
): RuntimeActivityView {
  const ordered = activities
    .map((activity, index) => ({ activity, index }))
    .sort(
      (left, right) =>
        (left.activity.sequence ?? left.index) -
        (right.activity.sequence ?? right.index),
    )
    .map(({ activity }) => activity);
  const failures = ordered.filter(
    (activity) => activity.status === "failed",
  );
  const completedTools = ordered.filter(
    (activity) =>
      activity.kind === "tool" && activity.status === "completed",
  );
  const milestones = buildMilestones(ordered, messageStatus).slice(
    -MAX_VISIBLE_MILESTONES,
  );

  if (messageStatus === "failed") {
    return {
      headline: failures.at(-1)?.label ?? "运行失败",
      detail:
        failures.length > 0
          ? `${failures.length} 个步骤失败`
          : "请稍后重试",
      tone: "failed",
      milestones,
    };
  }

  if (messageStatus === "stopped") {
    return {
      headline: "运行已停止",
      detail: completedToolDetail(completedTools, "已完成的步骤已保留"),
      tone: "stopped",
      milestones,
    };
  }

  if (messageStatus === "completed") {
    return {
      headline: failures.length > 0 ? "运行完成，但有步骤失败" : "任务已完成",
      detail:
        failures.length > 0
          ? `${failures.length} 个步骤失败`
          : completedToolDetail(completedTools, "查看关键步骤"),
      tone: failures.length > 0 ? "failed" : "completed",
      milestones,
    };
  }

  const latest = ordered[ordered.length - 1];
  return {
    headline: latest?.label ?? "正在处理请求",
    detail: completedToolDetail(completedTools, "正在处理，请稍候"),
    tone: "running",
    milestones,
  };
}

function buildMilestones(
  activities: RuntimeActivity[],
  messageStatus?: RuntimeMessageStatus,
): RuntimeActivity[] {
  const progressActivities = uniqueByLabel(
    activities.filter((activity) => activity.kind === "progress"),
  );
  const latestProgress = progressActivities[progressActivities.length - 1];
  const progressMilestones = progressActivities.map((activity) => {
    const isCurrent = activity.id === latestProgress?.id;
    const isRunning = isCurrent && messageStatus === "streaming";
    return {
      ...activity,
      id: `progress:${activity.label}`,
      label: isRunning ? activity.label : baseActivityLabel(activity.label),
      status: isRunning ? "running" : "completed",
    } satisfies RuntimeActivity;
  });

  const terminalToolGroups = new Map<
    string,
    { activity: RuntimeActivity; count: number; duration: number }
  >();
  activities.forEach((activity) => {
    if (activity.kind !== "tool" || !terminalStatuses.has(activity.status)) {
      return;
    }
    const key = `${activity.name ?? baseActivityLabel(activity.label)}:${activity.status}`;
    const existing = terminalToolGroups.get(key);
    terminalToolGroups.set(key, {
      activity,
      count: (existing?.count ?? 0) + 1,
      duration:
        (existing?.duration ?? 0) + Math.max(activity.duration_ms ?? 0, 0),
    });
  });
  const terminalTools = [...terminalToolGroups.entries()].map(
    ([key, group]) => ({
      ...group.activity,
      id: `tool-group:${key}`,
      label:
        group.count > 1
          ? `${baseActivityLabel(group.activity.label)} · ${group.count} 次`
          : baseActivityLabel(group.activity.label),
      duration_ms: group.duration > 0 ? group.duration : undefined,
    }),
  );

  const activeTools = activities.filter((activity, index) => {
    if (
      activity.kind !== "tool" ||
      (activity.status !== "started" && activity.status !== "running")
    ) {
      return false;
    }
    const key = activity.name ?? baseActivityLabel(activity.label);
    return !activities.slice(index + 1).some((later) => {
      const laterKey = later.name ?? baseActivityLabel(later.label);
      return (
        later.kind === "tool" &&
        laterKey === key &&
        terminalStatuses.has(later.status)
      );
    });
  });

  const modelActivities = activities.filter(
    (activity) => activity.kind === "model",
  );
  const latestModel = modelActivities[modelActivities.length - 1];
  const modelMilestone = latestModel
    ? [
        {
          ...latestModel,
          id: "model:latest",
          label:
            latestModel.status === "started" ||
            latestModel.status === "running"
              ? latestModel.label
              : "生成回答",
        },
      ]
    : [];

  const routeActivities = activities.filter(
    (activity) => activity.kind === "route",
  );
  const latestRoute = routeActivities[routeActivities.length - 1];
  const routeMilestone =
    progressMilestones.length === 0 && latestRoute
      ? [
          {
            ...latestRoute,
            id: "route:latest",
            label: "确定处理方式",
          },
        ]
      : [];

  return [
    ...routeMilestone,
    ...progressMilestones,
    ...terminalTools,
    ...activeTools,
    ...modelMilestone,
  ].sort(
    (left, right) =>
      (left.sequence ?? Number.MAX_SAFE_INTEGER) -
      (right.sequence ?? Number.MAX_SAFE_INTEGER),
  );
}

function uniqueByLabel(activities: RuntimeActivity[]): RuntimeActivity[] {
  const unique = new Map<string, RuntimeActivity>();
  activities.forEach((activity) => unique.set(activity.label, activity));
  return [...unique.values()];
}

function completedToolDetail(
  completedTools: RuntimeActivity[],
  fallback: string,
): string {
  if (completedTools.length === 0) return fallback;
  const labels = new Set(
    completedTools.map((activity) => baseActivityLabel(activity.label)),
  );
  if (labels.size === 1) {
    return `${completedTools.length} 次${[...labels][0]}`;
  }
  return `${completedTools.length} 次工具调用`;
}

function baseActivityLabel(label: string): string {
  return (
    label
      .replace(/^正在/, "")
      .replace(/(?:已取消|完成|失败)$/, "")
      .trim() || label
  );
}
