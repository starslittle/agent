import { afterEach, describe, expect, it, vi } from "vitest";

import { listProposals, resolveProposal } from "./proposal-api";

afterEach(() => vi.unstubAllGlobals());

describe("proposal API", () => {
  it("builds document and Run filters without changing credentials semantics", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [], has_more: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await listProposals({ documentID: "doc/1", runID: "run/1", statuses: ["pending", "deferred"], limit: 20 });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/wiki-proposals?limit=20&document_id=doc%2F1&run_id=run%2F1&status=pending%2Cdeferred",
    );
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("sends CSRF and idempotency data for an edited acceptance", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ proposal: { id: "proposal/1" }, replayed: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await resolveProposal("csrf-token", "proposal/1", "accept", "最终内容", "stable-key");

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/wiki-proposals/proposal%2F1/accept");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      credentials: "include",
      headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token", "Idempotency-Key": "stable-key" }),
      body: JSON.stringify({ final_content: "最终内容" }),
    });
  });

  it("maps a revision conflict to recoverable user guidance", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "wiki_proposal_target_conflict" }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    })));

    await expect(resolveProposal("csrf", "proposal", "accept", null, "key")).rejects.toThrow(
      "原上下文已发生变化。请刷新并重新比较后再决定。",
    );
  });
});
