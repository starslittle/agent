import { afterEach, describe, expect, it, vi } from "vitest";

import { getSkill, listSkills } from "./skill-api";

afterEach(() => vi.unstubAllGlobals());

describe("Skill API", () => {
  it("loads the authenticated effective catalog", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await listSkills();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/skills");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("encodes deep-link ids and hides internal unavailable reasons", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ error: "skill_not_available", internal_reason: "workflow_disabled" }), { status: 404, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getSkill("skill/one")).rejects.toThrow("这个 Skill 当前不可用。");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/skills/skill%2Fone");
  });
});
