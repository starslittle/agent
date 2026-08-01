export type SkillID = "research" | "fortune";

export interface VisibleSkill {
  id: SkillID;
  command: `/${SkillID}`;
  label: string;
  shortLabel: string;
  description: string;
}

export const VISIBLE_SKILLS: readonly VisibleSkill[] = [
  {
    id: "research",
    command: "/research",
    label: "深度研究",
    shortLabel: "研究",
    description: "检索、核验并综合外部信息",
  },
  {
    id: "fortune",
    command: "/fortune",
    label: "命理分析",
    shortLabel: "命理",
    description: "从命理叙事角度提供辅助分析",
  },
] as const;

export type SkillSelectionSource =
  | "direct"
  | "user"
  | "compatibility"
  | "automatic"
  | "fallback";

export function getVisibleSkill(skillID?: string | null): VisibleSkill | null {
  return VISIBLE_SKILLS.find((skill) => skill.id === skillID) ?? null;
}

export function filterVisibleSkills(query: string): readonly VisibleSkill[] {
  const normalized = query.trim().replace(/^\//, "").toLocaleLowerCase();
  if (!normalized) return VISIBLE_SKILLS;
  return VISIBLE_SKILLS.filter((skill) =>
    [skill.id, skill.label, skill.shortLabel, skill.description].some((value) =>
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

export function selectComposerSkill(
  state: SkillComposerState,
  skillID: SkillID,
): SkillComposerState {
  return {
    selectedSkill: skillID,
    value: state.value.replace(/^\/[^\s]*\s*/, ""),
  };
}

export function clearComposerSkill(state: SkillComposerState): SkillComposerState {
  return { ...state, selectedSkill: null };
}

export function explicitConfirmationTurn(
  prompt: string,
  skillID: SkillID,
): { text: string; requestedSkill: SkillID } {
  return { text: prompt, requestedSkill: skillID };
}
