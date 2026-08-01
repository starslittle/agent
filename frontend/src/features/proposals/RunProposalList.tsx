import { useEffect, useState } from "react";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { listProposals, type ProposalResolution, type WikiProposal } from "@/lib/proposal-api";

import { ProposalReviewCard } from "./ProposalReviewCard";

export function RunProposalList({ runID }: { runID: string }) {
  const { csrfToken } = useAuth();
  const [items, setItems] = useState<WikiProposal[]>([]);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    void listProposals({ runID, limit: 50 }, controller.signal)
      .then((response) => setItems(response.items))
      .catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取本次 Run 的候选。"); });
    return () => controller.abort();
  }, [reload, runID]);

  const resolved = (result: ProposalResolution) => {
    setItems((current) => current.map((item) => item.id === result.proposal.id ? result.proposal : item));
  };

  if (items.length === 0 && !error) return null;
  return <section className="mb-4 space-y-2" aria-label="本次运行产生的待确认信息">
    <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-semibold">本次 Run 的候选信息</h3><span className="text-[11px] text-muted-foreground">由你决定是否长期使用</span></div>
    {error && <div role="alert" className="rounded-lg border border-destructive/30 p-3 text-xs text-destructive">{error}<Button type="button" variant="link" size="sm" className="ml-2 h-auto px-0" onClick={() => setReload((value) => value + 1)}>重试</Button></div>}
    {items.map((proposal) => <ProposalReviewCard key={proposal.id} proposal={proposal} csrfToken={csrfToken} compact onResolved={resolved} onReload={() => setReload((value) => value + 1)} />)}
  </section>;
}
