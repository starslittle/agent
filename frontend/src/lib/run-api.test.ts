import { afterEach, describe, expect, it, vi } from "vitest";

import { getRunDetail, listRuns } from "./run-api";

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
});
