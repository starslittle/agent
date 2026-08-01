import { describe, expect, it } from "vitest";

import type { RuntimeActivity } from "@/lib/chat-api";
import { buildRuntimeActivityView } from "./runtime-activity-view";

const activities: RuntimeActivity[] = [
  {
    id: "1:tool.started",
    sequence: 1,
    kind: "tool",
    status: "started",
    label: "正在联网检索",
    name: "tavily_search",
  },
  {
    id: "2:tool.completed",
    sequence: 2,
    kind: "tool",
    status: "completed",
    label: "联网检索完成",
    name: "tavily_search",
  },
];

describe("buildRuntimeActivityView", () => {
  it("shows the latest meaningful state without exposing raw event counts", () => {
    expect(buildRuntimeActivityView(activities, "streaming")).toMatchObject({
      headline: "联网检索完成",
      detail: "1 次联网检索",
      tone: "running",
    });
  });

  it("collapses repeated tool start and completion events into one milestone", () => {
    const repeated = [
      ...activities,
      { ...activities[0], id: "3:tool.started", sequence: 3 },
      { ...activities[1], id: "4:tool.completed", sequence: 4 },
      { ...activities[0], id: "5:tool.started", sequence: 5 },
      { ...activities[1], id: "6:tool.completed", sequence: 6 },
    ];
    const view = buildRuntimeActivityView(repeated, "completed");

    expect(view).toMatchObject({
      headline: "任务已完成",
      detail: "3 次联网检索",
      tone: "completed",
    });
    expect(view.milestones).toHaveLength(1);
    expect(view.milestones[0]).toMatchObject({
      label: "联网检索 · 3 次",
      status: "completed",
    });
  });

  it("keeps a currently unmatched tool call visible", () => {
    const running = [
      ...activities,
      { ...activities[0], id: "3:tool.started", sequence: 3 },
    ];
    const view = buildRuntimeActivityView(running, "streaming");

    expect(view.milestones.map((milestone) => milestone.label)).toEqual([
      "联网检索",
      "正在联网检索",
    ]);
  });

  it("reports stopped and failed terminals truthfully", () => {
    expect(buildRuntimeActivityView(activities, "stopped")).toMatchObject({
      headline: "运行已停止",
      tone: "stopped",
    });

    const failed: RuntimeActivity[] = [
      ...activities,
      {
        id: "3:tool.failed",
        sequence: 3,
        kind: "tool",
        status: "failed",
        label: "联网检索失败",
        name: "tavily_search",
      },
    ];
    expect(buildRuntimeActivityView(failed, "failed")).toMatchObject({
      headline: "联网检索失败",
      detail: "1 个步骤失败",
      tone: "failed",
    });
  });
});
