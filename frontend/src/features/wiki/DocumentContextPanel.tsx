import { useEffect, useState } from "react";
import { ArrowUpRight, Brain, CircleAlert, FileCheck2, LoaderCircle, Plus, RefreshCw, Scale, Sparkles, WandSparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { createWikiItem, listWikiItems, type WikiItem, type WikiType } from "@/lib/wiki-api";
import { documentExtractionIdempotencyKey, startDocumentExtraction, type ExtractionRunStatus } from "@/lib/document-api";
import { getRunDetail } from "@/lib/run-api";
import { listProposals, type ProposalResolution, type WikiProposal } from "@/lib/proposal-api";
import { ProposalReviewCard } from "@/features/proposals/ProposalReviewCard";
import { parseProposalSourceDetail } from "@/features/proposals/proposal-presentation";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

const typeCopy: Record<WikiType, { label: string; icon: typeof Brain }> = {
  confirmed_fact: { label: "确认事实", icon: FileCheck2 },
  current_state: { label: "当前状态", icon: CircleAlert },
  personal_rule: { label: "个人规则", icon: Scale },
  ai_analysis: { label: "AI 分析", icon: Sparkles },
};

interface DocumentContextPanelProps {
  documentID: string;
  documentRevisionID: string;
  className?: string;
}

export function DocumentContextPanel({ documentID, documentRevisionID, className = "" }: DocumentContextPanelProps) {
  const { csrfToken } = useAuth();
  const [items, setItems] = useState<WikiItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<WikiType>("current_state");
  const [domain, setDomain] = useState("general");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [extractionRun, setExtractionRun] = useState<{ id: string; status: ExtractionRunStatus } | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState("");
  const [proposals, setProposals] = useState<WikiProposal[]>([]);
  const [showPending, setShowPending] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [proposalReload, setProposalReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listWikiItems(documentID, false, controller.signal)
      .then((response) => setItems(response.items))
      .catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取关联上下文"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [documentID, retry]);

  useEffect(() => {
    if (!extractionRun || ["completed", "cancelled", "failed", "timed_out"].includes(extractionRun.status)) return;
    let disposed = false;
    const poll = async () => {
      try {
        const detail = await getRunDetail(extractionRun.id);
        if (disposed) return;
        setExtractionRun({ id: detail.run.id, status: detail.run.status });
        if (detail.run.status === "completed") {
          const response = await listProposals({ documentID, limit: 100 });
          if (!disposed) setProposals(response.items);
        }
      } catch (reason) {
        if (!disposed) setExtractionError(reason instanceof Error ? reason.message : "无法读取提取进度");
      }
    };
    const timer = window.setInterval(() => void poll(), 1400);
    void poll();
    return () => { disposed = true; window.clearInterval(timer); };
  }, [documentID, documentRevisionID, extractionRun]);

  useEffect(() => {
    const controller = new AbortController();
    void listProposals({ documentID, limit: 100 }, controller.signal)
      .then((response) => setProposals(response.items))
      .catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setExtractionError(reason instanceof Error ? reason.message : "无法读取待确认候选"); });
    return () => controller.abort();
  }, [documentID, documentRevisionID, proposalReload]);

  const extract = async () => {
    if (extracting) return;
    setExtracting(true);
    setExtractionError("");
    setShowPending(false);
    try {
      const retryingFailure = extractionRun !== null && ["cancelled", "failed", "timed_out"].includes(extractionRun.status);
      const run = await startDocumentExtraction(
        csrfToken,
        documentID,
        documentExtractionIdempotencyKey(
          documentRevisionID,
          retryingFailure ? crypto.randomUUID() : undefined,
        ),
      );
      setExtractionRun({ id: run.run_id, status: run.status });
    } catch (reason) {
      setExtractionError(reason instanceof Error ? reason.message : "文档提取没有启动");
    } finally {
      setExtracting(false);
    }
  };

  const actionableProposals = proposals.filter((proposal) => proposal.status === "pending" || proposal.status === "deferred");
  const proposalHistory = proposals.filter((proposal) => proposal.status !== "pending" && proposal.status !== "deferred");
  const proposalFlags = actionableProposals.reduce((summary, proposal) => {
    try {
      const detail = parseProposalSourceDetail(proposal);
      if (detail.low_confidence) summary.low += 1;
      if ((detail.conflict_item_ids?.length || 0) > 0 || proposal.operation === "update") summary.conflicts += 1;
    } catch { /* malformed legacy details remain visible without derived flags */ }
    return summary;
  }, { low: 0, conflicts: 0 });

  const terminalFailure = extractionRun && ["cancelled", "failed", "timed_out"].includes(extractionRun.status);
  const runActive = extractionRun && ["queued", "running", "cancel_requested"].includes(extractionRun.status);

  const proposalResolved = (result: ProposalResolution) => {
    setProposals((current) => current.map((proposal) => proposal.id === result.proposal.id ? result.proposal : proposal));
    if (result.proposal.status === "accepted") setRetry((value) => value + 1);
  };

  const create = async () => {
    if (!content.trim() || saving) return;
    setSaving(true);
    try {
      await createWikiItem(csrfToken, { type, domain, content: content.trim(), document_id: documentID, document_revision_id: documentRevisionID });
      toast.success("已加入关联上下文");
      setContent("");
      setOpen(false);
      setRetry((value) => value + 1);
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : "保存没有完成"); }
    finally { setSaving(false); }
  };

  return (
    <aside className={`flex h-full min-h-0 flex-col bg-muted/20 ${className}`} aria-label="关联上下文">
      <div className="flex items-start justify-between gap-3 border-b px-5 py-5">
        <div><h2 className="text-sm font-semibold">关联上下文</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">经你确认后，才会长期影响回答。</p></div>
        <Button type="button" variant="outline" size="icon" className="h-11 w-11" onClick={() => setOpen(true)} aria-label="添加关联上下文"><Plus className="h-4 w-4" aria-hidden="true" /></Button>
      </div>
      <section className="border-b bg-background/70 p-3" aria-labelledby="document-extraction-title">
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"><WandSparkles className="h-4 w-4" aria-hidden="true" /></span>
            <div className="min-w-0 flex-1">
              <h3 id="document-extraction-title" className="text-sm font-medium">从当前版本提取</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">只分析这篇文档。结果先进入待确认，不会直接改变长期上下文。</p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2" aria-live="polite">
            <Button type="button" size="sm" onClick={() => void extract()} disabled={extracting || Boolean(runActive)}>
              {(extracting || runActive) && <LoaderCircle className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden="true" />}
              {runActive ? "正在提取" : terminalFailure ? "重新提取" : "提取候选信息"}
            </Button>
            {extractionRun && <Button asChild variant="ghost" size="sm"><Link to={`/agent-runs/${encodeURIComponent(extractionRun.id)}`}>查看 Run <ArrowUpRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" /></Link></Button>}
          </div>
          {extractionError && <p role="alert" className="mt-3 text-xs leading-5 text-destructive">{extractionError}</p>}
          {terminalFailure && !extractionError && <p role="status" className="mt-3 text-xs leading-5 text-destructive">本次提取未完成，没有写入文档或长期上下文。</p>}
          {actionableProposals.length > 0 && <div className="mt-3 rounded-lg bg-muted/60 p-3 text-xs"><p className="font-medium">{actionableProposals.length} 条待你决定</p><p className="mt-1 text-muted-foreground">{proposalFlags.conflicts} 条可能冲突 · {proposalFlags.low} 条低置信度</p><Button type="button" variant="link" size="sm" className="mt-1 min-h-11 px-0" onClick={() => setShowPending((value) => !value)}>{showPending ? "收起候选" : "逐条确认"}</Button></div>}
          {showPending && <div className="mt-2 space-y-2">{actionableProposals.map((proposal) => <ProposalReviewCard key={proposal.id} proposal={proposal} csrfToken={csrfToken} compact onResolved={proposalResolved} onReload={() => setProposalReload((value) => value + 1)} />)}</div>}
          {proposalHistory.length > 0 && <Collapsible open={showHistory} onOpenChange={setShowHistory} className="mt-3"><CollapsibleTrigger asChild><Button type="button" variant="ghost" size="sm" className="min-h-11 w-full justify-between">处理记录（{proposalHistory.length}）<span aria-hidden="true">{showHistory ? "−" : "+"}</span></Button></CollapsibleTrigger><CollapsibleContent className="mt-2 space-y-2">{proposalHistory.map((proposal) => <ProposalReviewCard key={proposal.id} proposal={proposal} csrfToken={csrfToken} compact onResolved={proposalResolved} onReload={() => setProposalReload((value) => value + 1)} />)}</CollapsibleContent></Collapsible>}
        </div>
      </section>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain p-3">
        {loading && <p role="status" className="px-3 py-10 text-center text-xs text-muted-foreground">正在读取上下文…</p>}
        {!loading && error && <div role="alert" className="px-3 py-8 text-center"><p className="text-xs text-destructive">{error}</p><Button variant="ghost" size="sm" className="mt-2" onClick={() => setRetry((value) => value + 1)}><RefreshCw className="mr-2 h-3.5 w-3.5" aria-hidden="true" />重试</Button></div>}
        {!loading && !error && items.length === 0 && <div className="px-4 py-10 text-center"><Brain className="mx-auto h-7 w-7 text-primary/60" aria-hidden="true" /><p className="mt-3 text-sm font-medium">还没有关联信息</p><p className="mt-1 text-xs leading-5 text-muted-foreground">从文档中挑出值得长期保留的事实、状态或规则。</p></div>}
        {!loading && !error && items.map((item) => {
          const copy = typeCopy[item.type]; const Icon = copy.icon;
          const statusLabel = item.type === "ai_analysis" && item.status === "confirmed" ? "用户保留" : item.status === "confirmed" ? "已确认" : item.status === "outdated" ? "已过时" : item.status;
          return <Link key={item.id} to={`/space/context/${item.id}`} className="block rounded-xl border bg-background p-4 transition-colors hover:border-primary/30 hover:bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-center gap-2 text-xs font-medium"><Icon className="h-4 w-4 text-primary" aria-hidden="true" />{copy.label}<span className="ml-auto rounded-full bg-muted px-2 py-1 text-xs text-muted-foreground">{statusLabel}</span></div><p className="mt-3 line-clamp-3 text-xs leading-5 text-muted-foreground">{item.content}</p></Link>;
        })}
      </div>

      <Dialog open={open} onOpenChange={setOpen}><DialogContent><DialogHeader><DialogTitle>添加关联上下文</DialogTitle><DialogDescription>这里保存的是你明确认可的信息，不是 AI 的临时推测。</DialogDescription></DialogHeader><div className="space-y-4 py-2"><div className="space-y-2"><Label htmlFor="context-type">类型</Label><Select value={type} onValueChange={(value: WikiType) => setType(value)}><SelectTrigger id="context-type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="confirmed_fact">确认事实</SelectItem><SelectItem value="current_state">当前状态</SelectItem><SelectItem value="personal_rule">个人规则</SelectItem><SelectItem value="ai_analysis">AI 分析</SelectItem></SelectContent></Select></div><div className="space-y-2"><Label htmlFor="context-domain">领域</Label><Input id="context-domain" name="context-domain" autoComplete="off" value={domain} onChange={(event) => setDomain(event.target.value)} placeholder="例如：career…" /></div><div className="space-y-2"><Label htmlFor="context-content">内容</Label><Textarea id="context-content" name="context-content" value={content} onChange={(event) => setContent(event.target.value)} rows={6} placeholder="写下需要启点长期记住的信息…" /></div></div><DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>取消</Button><Button onClick={() => void create()} disabled={!content.trim() || !domain.trim() || saving}>{saving ? "正在保存…" : "确认并保存"}</Button></DialogFooter></DialogContent></Dialog>
    </aside>
  );
}
