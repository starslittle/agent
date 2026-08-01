import { createContext, useContext } from "react";

import type { PublicSkill } from "@/lib/skill-api";

export interface SkillCatalogState {
  skills: PublicSkill[];
  loading: boolean;
  error: string;
  reload: () => void;
}

export const SkillCatalogContext = createContext<SkillCatalogState>({
  skills: [],
  loading: false,
  error: "",
  reload: () => undefined,
});

export function useSkillCatalog(): SkillCatalogState {
  return useContext(SkillCatalogContext);
}
