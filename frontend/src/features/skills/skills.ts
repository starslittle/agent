import type { PublicSkill } from "@/lib/skill-api";

export type SkillID = string;

export type SkillSelectionSource =
  | "direct"
  | "user"
  | "compatibility"
  | "automatic"
  | "fallback";

export function getVisibleSkill(skills: readonly PublicSkill[], skillID?: string | null): PublicSkill | null {
  return skills.find((skill) => skill.id === skillID) ?? null;
}

export function filterVisibleSkills(skills: readonly PublicSkill[], query: string): readonly PublicSkill[] {
  const normalized = query.trim().replace(/^\//, "").toLocaleLowerCase();
  if (!normalized) return skills;
  return skills.filter((skill) =>
    [skill.id, skill.title, skill.command, skill.description, skill.public_purpose].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    ),
  );
}

export function skillSourceLabel(source?: SkillSelectionSource | null): string {
  switch (source) {
    case "user":
      return "由你指定";
    case "automatic":
      return "启点自动选择";
    case "compatibility":
      return "兼容模式";
    case "fallback":
      return "默认回退";
    case "direct":
    default:
      return "直接回答";
  }
}

export interface SkillComposerState {
  selectedSkill: SkillID | null;
  value: string;
}

export function selectComposerSkill(state: SkillComposerState, skillID: SkillID): SkillComposerState {
  return { selectedSkill: skillID, value: state.value.replace(/^\/[^\s]*\s*/, "") };
}

export function clearComposerSkill(state: SkillComposerState): SkillComposerState {
  return { ...state, selectedSkill: null };
}

export function explicitConfirmationTurn(prompt: string, skillID: SkillID): { text: string; requestedSkill: SkillID } {
  return { text: prompt, requestedSkill: skillID };
}
