import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { listSkills, type PublicSkill } from "@/lib/skill-api";
import { SkillCatalogContext } from "./skill-catalog-context";

export function SkillCatalogProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [skills, setSkills] = useState<PublicSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    if (!user) {
      setSkills([]);
      setLoading(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listSkills(controller.signal)
      .then((response) => setSkills(response.items))
      .catch((reason: unknown) => {
        if ((reason as Error).name !== "AbortError") {
          setSkills([]);
          setError(reason instanceof Error ? reason.message : "暂时无法读取可用 Skills。请重试。");
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision, user]);

  const value = useMemo(() => ({ skills, loading, error, reload }), [error, loading, reload, skills]);
  return <SkillCatalogContext.Provider value={value}>{children}</SkillCatalogContext.Provider>;
}
