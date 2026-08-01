import { describe, expect, it } from "vitest";

import type { PublicSkill } from "@/lib/skill-api";

import {
  filterVisibleSkills,
  clearComposerSkill,
  explicitConfirmationTurn,
  getVisibleSkill,
  skillSourceLabel,
  selectComposerSkill,
} from "./skills";

const skill = (id: string, title: string, purpose: string): PublicSkill => ({
  id,
  version: 1,
  title,
  description: purpose,
  command: `/${id}`,
  public_purpose: purpose,
  public_capabilities: [],
  context_scope: [],
  confirmation_summary: "由你确认",
  may_propose_updates: false,
  available: true,
  effective: true,
});

const catalog = [
  skill("research", "深度研究", "检索、核验并综合外部信息"),
  skill("fortune", "命理分析", "从命理叙事角度提供辅助分析"),
];

describe("server-backed Skill catalog helpers", () => {
  it("filters the supplied effective catalog instead of owning a static list", () => {
    expect(filterVisibleSkills(catalog, "/res").map((item) => item.id)).toEqual(["research"]);
    expect(filterVisibleSkills(catalog, "命理").map((item) => item.id)).toEqual(["fortune"]);
  });

  it("does not invent unavailable skills", () => {
    expect(getVisibleSkill(catalog, "decision")).toBeNull();
    expect(skillSourceLabel("automatic")).toBe("启点自动选择");
  });

  it("turns a slash selection into a removable per-message chip state", () => {
    const selected = selectComposerSkill({ selectedSkill: null, value: "/fortune 请分析这个问题" }, "fortune");
    expect(selected).toEqual({ selectedSkill: "fortune", value: "请分析这个问题" });
    expect(clearComposerSkill(selected)).toEqual({ selectedSkill: null, value: "请分析这个问题" });
  });

  it("creates confirmation as a new explicit Skill turn", () => {
    expect(explicitConfirmationTurn("继续原问题", "research")).toEqual({ text: "继续原问题", requestedSkill: "research" });
  });
});
