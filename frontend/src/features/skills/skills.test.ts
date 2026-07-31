import { describe, expect, it } from "vitest";

import {
  filterVisibleSkills,
  clearComposerSkill,
  explicitConfirmationTurn,
  getVisibleSkill,
  skillSourceLabel,
  selectComposerSkill,
  VISIBLE_SKILLS,
} from "./skills";

describe("visible Skill catalog", () => {
  it("only exposes the registered and user-visible ROUND-02 skills", () => {
    expect(VISIBLE_SKILLS.map((skill) => skill.id)).toEqual([
      "research",
      "fortune",
    ]);
  });

  it("filters slash commands by id and Chinese label", () => {
    expect(filterVisibleSkills("/res").map((skill) => skill.id)).toEqual([
      "research",
    ]);
    expect(filterVisibleSkills("命理").map((skill) => skill.id)).toEqual([
      "fortune",
    ]);
  });

  it("does not invent unavailable skills", () => {
    expect(getVisibleSkill("decision")).toBeNull();
    expect(skillSourceLabel("automatic")).toBe("启点自动选择");
  });

  it("turns a slash selection into a removable per-message chip state", () => {
    const selected = selectComposerSkill(
      { selectedSkill: null, value: "/fortune 请分析这个问题" },
      "fortune",
    );
    expect(selected).toEqual({
      selectedSkill: "fortune",
      value: "请分析这个问题",
    });
    expect(clearComposerSkill(selected)).toEqual({
      selectedSkill: null,
      value: "请分析这个问题",
    });
  });

  it("creates confirmation as a new explicit Skill turn", () => {
    expect(explicitConfirmationTurn("继续原问题", "research")).toEqual({
      text: "继续原问题",
      requestedSkill: "research",
    });
  });
});
