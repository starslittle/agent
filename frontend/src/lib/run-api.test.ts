import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getObservableRunDetail,
  getRunDetail,
  listObservableRuns,
  listRuns,
} from "./run-api";

afterEach(() => vi.unstubAllGlobals());

describe("Run API", () => {
  it("requests a filtered cursor page", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ items: [], next_before: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await listRuns({
      status: "failed",
      before: "2026-08-01T00:00:00Z",
      limit: 20,
    });

    expect(response.items).toEqual([]);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/agent-runs?limit=20&status=failed&before=2026-08-01T00%3A00%3A00Z",
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("loads detail by an encoded run id", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ run: { id: "run/1" }, spans: [], events: [], prompts: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getRunDetail("run/1");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/agent-runs/run%2F1");
  });

  it("surfaces the server-safe failure message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ message: "运行不存在" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(getRunDetail("missing")).rejects.toThrow("运行不存在");
  });

  it("builds the internal read-only filter request", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await listObservableRuns({
      userID: "user-1",
      skill: "research",
      workflow: "research_graph",
      model: "auto",
      status: "failed",
      errorCode: "tool_failed",
      from: "2026-08-01T00:00:00Z",
      to: "2026-08-02T00:00:00Z",
      limit: 20,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/internal/agent-runs?limit=20&user_id=user-1&skill=research&workflow=research_graph&model=auto&status=failed&error_code=tool_failed&from=2026-08-01T00%3A00%3A00Z&to=2026-08-02T00%3A00%3A00Z",
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("method");
  });

  it("uses only GET semantics for internal detail", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      run: { id: "run/1" }, spans: [], events: [], prompts: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await getObservableRunDetail("run/1");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/internal/agent-runs/run%2F1");
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("method");
  });
});
