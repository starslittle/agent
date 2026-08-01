import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, ArrowUpRight, Check, ChevronDown, Clock3, FileText, LoaderCircle, Pencil, ShieldCheck, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getProposal, resolveProposal, type ProposalAction, type ProposalDetail, type ProposalResolution, type WikiProposal } from "@/lib/proposal-api";

import { parseProposalSourceDetail, proposalStatusLabels, proposalTypeLabels } from "./proposal-presentation";

interface ProposalReviewCardProps {
  proposal: WikiProposal;
  csrfToken: string;
  onResolved: (resolution: ProposalResolution) => void;
  onReload: () => void;
  compact?: boolean;
}

function nextID(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `proposal-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function ProposalReviewCard({ proposal, csrfToken, onResolved, onReload, compact = false }: ProposalReviewCardProps) {
  const source = useMemo(() => parseProposalSourceDetail(proposal), [proposal]);
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<ProposalDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<ProposalAction | "edit" | null>(null);
  const [error, setError] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [draft, setDraft] = useState(proposal.proposed_content);
  const keys = useRef(new Map<string, string>());
  const actionable = proposal.status === "pending" || proposal.status === "deferred";
  const conflictCount = source.conflict_item_ids?.length || (proposal.operation === "update" ? 1 : 0);
  const runID = source.run_id || source.origin_run_id;

  useEffect(() => {
    if (!expanded || detail) return;
    const controller = new AbortController();
    setDetailLoading(true);
    void getProposal(proposal.id, controller.signal)
      .then(setDetail)
      .catch((reason: unknown) => {
        if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取候选依据。请重试。");
      })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [detail, expanded, proposal.id]);

  const perform = async (action: ProposalAction, finalContent: string | null = null) => {
    if (busyAction) return;
    const normalized = finalContent?.trim() || null;
    const signature = `${proposal.id}:${action}:${normalized || ""}`;
    const key = keys.current.get(signature) || nextID();
    keys.current.set(signature, key);
    setBusyAction(action === "accept" && normalized ? "edit" : action);
    setError("");
    try {
      const result = await resolveProposal(csrfToken, proposal.id, action, normalized, key);
      onResolved(result);
      setEditOpen(false);
      setRejectOpen(false);
      const label = action === "accept" ? "已接受，后续回答可使用这条上下文" : action === "defer" ? "已暂缓，可稍后继续处理" : "已拒绝，不会进入后续上下文";
      toast.success(label);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "候选操作没有完成。请重试。");
    } finally {
      setBusyAction(null);
    }
  };

  const requestEditOpen = (open: boolean) => {
    if (!open && draft.trim() !== proposal.proposed_content && !window.confirm("放弃尚未确认的修改吗？")) return;
    if (open) setDraft(proposal.proposed_content);
    setEditOpen(open);
  };

  return (
    <article className="rounded-xl border bg-background p-4 shadow-sm" aria-labelledby={`proposal-${proposal.id}`}>
      <div className="flex min-w-0 items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 id={`proposal-${proposal.id}`} className="text-sm font-semibold text-pretty">{proposalTypeLabels[proposal.item_type]}</h4>
            <span className="rounded-full bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground">{proposalStatusLabels[proposal.status]}</span>
            {source.confidence !== undefined && <span className="tabular-nums text-[11px] text-muted-foreground">置信度 {new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 0 }).format(source.confidence)}</span>}
          </div>
          <p className="mt-1 truncate text-[11px] text-muted-foreground">{proposal.domain} · {proposal.operation === "update" ? "建议更新已有信息" : "建议新增信息"}</p>
        </div>
      </div>

      <div className="mt-4 rounded-lg border-l-2 border-primary/40 bg-muted/45 px-3 py-2.5">
        <p className="text-[11px] font-medium text-muted-foreground">建议内容</p>
        <p className="mt-1 break-words text-sm leading-6 text-foreground">{proposal.proposed_content}</p>
      </div>

      {(conflictCount > 0 || source.low_confidence) && <div className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-xs leading-5" role="note"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" /><p><span className="font-medium text-foreground">需要多看一眼。</span> {conflictCount > 0 ? `${conflictCount} 条已有信息可能与它冲突。` : ""}{source.low_confidence ? " 这条候选置信度较低。" : ""}</p></div>}

      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger asChild>
          <Button type="button" variant="ghost" size="sm" className="mt-2 min-h-11 w-full justify-between px-2">
            查看原文与依据
            <ChevronDown className={`h-4 w-4 transition-transform motion-reduce:transition-none ${expanded ? "rotate-180" : ""}`} aria-hidden="true" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 border-t pt-3 text-xs">
          {detailLoading && <p role="status" className="flex items-center gap-2 text-muted-foreground"><LoaderCircle className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />正在读取依据…</p>}
          {detail?.target && <div><p className="font-medium text-muted-foreground">已有内容</p><p className="mt-1 break-words rounded-lg bg-muted/50 p-3 leading-5">{detail.target.revision.content}</p></div>}
          {source.source_excerpt && <div><p className="font-medium text-muted-foreground">原文片段</p><blockquote className="mt-1 break-words border-l-2 pl-3 leading-5 text-muted-foreground">{source.source_excerpt}</blockquote></div>}
          {source.explanation && <div><p className="font-medium text-muted-foreground">为什么建议保留</p><p className="mt-1 break-words leading-5 text-muted-foreground">{source.explanation}</p></div>}
          <div className="flex flex-wrap gap-2">
            {proposal.document_id && <Button asChild variant="outline" size="sm" className="min-h-11"><Link to={`/space/documents/${encodeURIComponent(proposal.document_id)}?revision=${encodeURIComponent(proposal.document_revision_id || "")}`}><FileText className="mr-2 h-3.5 w-3.5" aria-hidden="true" />返回来源文档 <ArrowUpRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" /></Link></Button>}
            {runID && <Button asChild variant="outline" size="sm" className="min-h-11"><Link to={`/agent-runs/${encodeURIComponent(runID)}`}>查看 Run <ArrowUpRight className="ml-1 h-3.5 w-3.5" aria-hidden="true" /></Link></Button>}
          </div>
          {proposal.document_revision_id && <p className="break-all font-mono text-[10px] text-muted-foreground" translate="no">Document Revision {proposal.document_revision_id}</p>}
        </CollapsibleContent>
      </Collapsible>

      {proposal.status === "accepted" && <div className="mt-3 flex items-start gap-2 rounded-lg bg-primary/10 p-3 text-xs leading-5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" /><div><p className="font-medium">已写入关联上下文</p>{proposal.final_content && proposal.final_content !== proposal.proposed_content && <><p className="mt-2 text-muted-foreground">最终采用</p><p className="mt-1 break-words">{proposal.final_content}</p></>}</div></div>}
      {proposal.status === "rejected" && <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><X className="h-4 w-4" aria-hidden="true" />已拒绝，不会进入默认上下文。</p>}
      {proposal.status === "deferred" && <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="h-4 w-4" aria-hidden="true" />已暂缓，仍可在这里继续处理。</p>}

      {actionable && <div className={`mt-4 grid gap-2 ${compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4"}`} aria-live="polite">
        <Button type="button" className="min-h-11" onClick={() => void perform("accept")} disabled={Boolean(busyAction)}>{busyAction === "accept" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check className="mr-2 h-4 w-4" aria-hidden="true" />}接受</Button>
        <Button type="button" variant="outline" className="min-h-11" onClick={() => requestEditOpen(true)} disabled={Boolean(busyAction)}><Pencil className="mr-2 h-4 w-4" aria-hidden="true" />修改后接受</Button>
        <Button type="button" variant="outline" className="min-h-11" onClick={() => void perform("defer")} disabled={Boolean(busyAction)}>{busyAction === "defer" && <LoaderCircle className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}暂缓</Button>
        <Button type="button" variant="ghost" className="min-h-11 text-destructive hover:text-destructive" onClick={() => setRejectOpen(true)} disabled={Boolean(busyAction)}>拒绝</Button>
      </div>}
      {error && <div className="mt-3 rounded-lg border border-destructive/30 p-3" role="alert"><p className="text-xs leading-5 text-destructive">{error}</p><Button type="button" variant="link" size="sm" className="mt-1 h-auto px-0" onClick={onReload}>刷新状态后重试</Button></div>}

      <Dialog open={editOpen} onOpenChange={requestEditOpen}>
        <DialogContent className="max-h-[min(90dvh,42rem)] overflow-y-auto overscroll-contain sm:max-w-xl">
          <DialogHeader><DialogTitle>修改后接受</DialogTitle><DialogDescription>原建议会保留在审计记录中，只有下方最终内容会进入关联上下文。Markdown 原文不会改变。</DialogDescription></DialogHeader>
          <div className="space-y-4 py-2"><div className="rounded-lg bg-muted/50 p-3 text-xs leading-5 text-muted-foreground"><p className="font-medium text-foreground">原建议</p><p className="mt-1 break-words">{proposal.proposed_content}</p></div><div className="space-y-2"><Label htmlFor={`proposal-final-${proposal.id}`}>最终内容</Label><Textarea id={`proposal-final-${proposal.id}`} name="proposal-final-content" autoComplete="off" rows={7} value={draft} onChange={(event) => setDraft(event.target.value)} className="resize-y text-base leading-6" /><p className="text-xs text-muted-foreground">写成以后看到时仍能独立理解的一句话。</p></div></div>
          <DialogFooter><Button type="button" variant="outline" onClick={() => requestEditOpen(false)}>取消</Button><Button type="button" onClick={() => void perform("accept", draft)} disabled={Boolean(busyAction) || !draft.trim()}>{busyAction === "edit" && <LoaderCircle className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}接受最终内容</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>拒绝这条候选？</AlertDialogTitle><AlertDialogDescription>拒绝后它不会进入后续回答使用的上下文。文档原文与处理记录仍会保留。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>返回检查</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => void perform("reject")}>确认拒绝</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
      </AlertDialog>
    </article>
  );
}
