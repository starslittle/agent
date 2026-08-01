import { afterEach, describe, expect, it, vi } from "vitest";

import { listSpaceEntries, updateDocument } from "./space-api";

afterEach(() => vi.unstubAllGlobals());

describe("space API", () => {
  it("keeps sort and folder location in the URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], limit: 100, offset: 0, has_more: false }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await listSpaceEntries("folder id", "recent");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("parent_id=folder+id"), expect.objectContaining({ credentials: "include" }));
    expect(fetchMock.mock.calls[0][0]).toContain("sort=recent");
  });

  it("sends CSRF and optimistic version on document writes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: "doc" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await updateDocument("csrf-token", "doc", "# next", 4);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PATCH");
    expect(init.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
    expect(JSON.parse(init.body as string)).toEqual({ content: "# next", expected_version: 4 });
  });
});
