import { describe, expect, it } from "vitest";

import type { RunEvent } from "@/lib/run-api";
import {
  formatDuration,
  RUN_STATUS,
  safeArtifact,
  safeCitation,
  stableRunEvents,
} from "./run-presentation";

function event(sequence: number, type: string, data: Record<string, unknown> = {}): RunEvent {
  return {
    sequence,
    type,
    occurred_at: `2026-08-01T00:00:0${sequence}Z`,
    trace_id: "trace-1",
    event_schema_version: 1,
    content_capture_level: "metadata",
    data,
  };
}

describe("Run presentation", () => {
  it("maps every terminal and active status", () => {
    expect(Object.keys(RUN_STATUS)).toEqual([
      "queued",
      "running",
      "cancel_requested",
      "completed",
      "cancelled",
      "failed",
      "timed_out",
    ]);
  });

  it("sorts events stably by sequence before time", () => {
    expect(stableRunEvents([event(3, "run.completed"), event(1, "run.started"), event(2, "progress")]).map((item) => item.sequence)).toEqual([1, 2, 3]);
  });

  it("only projects allow-listed citation and artifact fields", () => {
    const citation = safeCitation(event(1, "citation.created", {
      citation_id: "source-1",
      title: "来源",
      url: "https://example.com/report",
      snippet: "公开摘要",
      prompt: "must-not-render",
      secret: "must-not-render",
    }));
    expect(citation).toEqual({
      id: "source-1",
      title: "来源",
      url: "https://example.com/report",
      snippet: "公开摘要",
    });
    expect(JSON.stringify(citation)).not.toContain("must-not-render");

    expect(safeArtifact(event(2, "artifact.created", {
      artifact_id: "report:1",
      artifact_type: "research_report",
      media_type: "application/json",
      size_bytes: 42,
      content: "must-not-render",
    }))).toEqual({
      id: "report:1",
      type: "research_report",
      mediaType: "application/json",
      sizeBytes: 42,
    });
  });

  it("formats short and long durations", () => {
    expect(formatDuration(42)).toBe("42ms");
    expect(formatDuration(18_400)).toBe("18.4s");
    expect(formatDuration(65_000)).toBe("1m 5s");
  });
});
