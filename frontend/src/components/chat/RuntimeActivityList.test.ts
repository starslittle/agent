import { describe, expect, it } from "vitest";

import type { RuntimeActivity } from "@/lib/chat-api";
import { runtimeActivitySummary } from "@/lib/conversation-stream-reducer";

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

describe("runtimeActivitySummary", () => {
  it("only reports running while the message is streaming", () => {
    expect(runtimeActivitySummary(activities, "streaming")).toBe(
      "正在运行 · 2 项活动",
    );
  });

  it("does not infer running from historical started activities after completion", () => {
    expect(runtimeActivitySummary(activities, "completed")).toBe(
      "运行过程 · 已完成 1 次工具调用",
    );
  });

  it("reports stopped and failed message terminals truthfully", () => {
    expect(runtimeActivitySummary(activities, "stopped")).toBe(
      "运行已停止 · 2 项活动",
    );
    expect(runtimeActivitySummary(activities, "failed")).toBe(
      "运行失败 · 2 项活动",
    );
  });
});
