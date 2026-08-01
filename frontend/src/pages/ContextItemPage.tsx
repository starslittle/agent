import { useEffect, useState } from "react";
import { Archive, ArrowLeft, RotateCcw, Save, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { changeWikiStatus, deleteWikiItem, getWikiItem, updateWikiItem, type WikiDetail } from "@/lib/wiki-api";

const typeLabels = { confirmed_fact: "确认事实", current_state: "当前状态", personal_rule: "个人规则", ai_analysis: "AI 分析" } as const;

export default function ContextItemPage() {
  const { itemId = "" } = useParams<{ itemId: string }>();
  const { csrfToken } = useAuth();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<WikiDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    void getWikiItem(itemId, controller.signal).then((value) => { setDetail(value); setDraft(value.item.content); }).catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取上下文"); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [itemId, retry]);

  const save = async () => {
    if (!detail || !draft.trim() || draft.trim() === detail.item.content || busy) return;
    setBusy(true);
    try { const value = await updateWikiItem(csrfToken, detail.item, draft.trim()); setDetail(value); setDraft(value.item.content); toast.success("上下文已更新并保留历史版本"); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "保存没有完成"); }
    finally { setBusy(false); }
  };
  const status = async (action: "outdated" | "forget" | "restore") => {
    if (!detail || busy) return;
    setBusy(true);
    try { await changeWikiStatus(csrfToken, detail.item, action); toast.success(action === "forget" ? "已暂时遗忘" : action === "restore" ? "已恢复" : "已标记为过时"); setRetry((value) => value + 1); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "状态更新没有完成"); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!detail || busy) return;
    setBusy(true);
    try { await deleteWikiItem(csrfToken, detail.item); toast.success("上下文已永久删除"); navigate(-1); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "删除没有完成"); setBusy(false); }
  };

  const sourceDocumentID = detail?.sources.find((source) => source.document_id)?.document_id;
  return <WorkspaceShell title="关联上下文" subtitle="查看来源、修改历史与记忆状态" mainId="context-main" mainClassName="overflow-y-auto">
    <div className="mx-auto w-full max-w-3xl px-4 py-7 sm:px-8 lg:py-12">
      <Button variant="ghost" asChild className="mb-7 -ml-3"><Link to={sourceDocumentID ? `/space/documents/${sourceDocumentID}` : "/space"}><ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />返回文档</Link></Button>
      {loading && <p role="status" className="py-20 text-center text-sm text-muted-foreground">正在读取上下文…</p>}
      {!loading && error && <div role="alert" className="py-20 text-center"><p className="text-sm text-destructive">{error}</p><Button variant="outline" className="mt-4" onClick={() => setRetry((value) => value + 1)}>重新加载</Button></div>}
      {!loading && detail && <>
        <header className="border-b pb-7"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-full bg-primary/10 px-3 py-1.5 font-medium text-primary">{typeLabels[detail.item.type]}</span><span className="rounded-full bg-muted px-3 py-1.5 text-muted-foreground">{detail.item.type === "ai_analysis" && detail.item.status === "confirmed" ? "用户保留" : detail.item.status === "confirmed" ? "已确认" : detail.item.status === "forgotten" ? "已遗忘" : detail.item.status === "outdated" ? "已过时" : detail.item.status}</span><span className="text-muted-foreground">第 {detail.item.revision_number} 版</span></div><h2 className="mt-5 text-balance text-2xl font-semibold tracking-tight">启点长期使用的结构化信息</h2><p className="mt-2 text-sm text-muted-foreground">领域：{detail.item.domain}</p></header>
        <section className="py-7"><label htmlFor="wiki-content" className="mb-2 block text-sm font-medium">内容</label><Textarea id="wiki-content" name="wiki-content" rows={10} value={draft} onChange={(event) => setDraft(event.target.value)} className="resize-y text-base leading-7" /><div className="mt-3 flex justify-end"><Button onClick={() => void save()} disabled={busy || !draft.trim() || draft.trim() === detail.item.content}><Save className="mr-2 h-4 w-4" aria-hidden="true" />{busy ? "正在保存…" : "保存新版本"}</Button></div></section>
        <section className="border-t py-7"><h3 className="text-sm font-semibold">来源</h3><div className="mt-3 space-y-2">{detail.sources.map((source) => <div key={source.id} className="rounded-xl border bg-card p-4 text-xs text-muted-foreground"><p className="font-medium text-foreground">{source.type === "document_extracted" ? "来自文档" : "用户输入"}</p><p className="mt-1 break-all">{source.document_revision_id ? `文档版本 ${source.document_revision_id}` : source.reference || "直接确认"}</p></div>)}</div></section>
		<section className="border-t py-7"><h3 className="text-sm font-semibold">使用记录</h3><p className="mt-2 text-xs leading-5 text-muted-foreground">这里只记录实际进入过 Context Package 的运行，不代表每次对话都会读取。</p>{detail.usage.length === 0 ? <p className="mt-3 rounded-xl border bg-card p-4 text-xs text-muted-foreground">还没有运行使用过这条上下文。</p> : <div className="mt-3 space-y-2">{detail.usage.map((usage) => <Link key={usage.package_id} to={`/agent-runs/${encodeURIComponent(usage.run_id)}`} className="block rounded-xl border bg-card p-4 text-xs hover:border-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="font-medium text-foreground">{usage.purpose}</span><span className="ml-2 text-muted-foreground">查看 Run 依据</span></Link>)}</div>}</section>
        <section className="border-t py-7"><h3 className="text-sm font-semibold">记忆状态</h3><p className="mt-2 text-xs leading-5 text-muted-foreground">暂时遗忘会保留历史，但退出默认检索。永久删除会清除正文和来源，仅留下无内容的删除记录。</p><div className="mt-4 flex flex-wrap gap-2">{detail.item.status === "forgotten" ? <Button variant="outline" onClick={() => void status("restore")} disabled={busy}><RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />恢复</Button> : <Button variant="outline" onClick={() => void status("forget")} disabled={busy}><Archive className="mr-2 h-4 w-4" aria-hidden="true" />暂时遗忘</Button>}{detail.item.status !== "outdated" && detail.item.status !== "forgotten" && <Button variant="outline" onClick={() => void status("outdated")} disabled={busy}>标记为过时</Button>}<Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => setDeleteOpen(true)}><Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />永久删除</Button></div></section>
      </>}
    </div>
    <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>永久删除这条上下文？</AlertDialogTitle><AlertDialogDescription>正文、版本与来源会被清除，且不能恢复。文档、对话和 Run 不会被删除。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => void remove()}>永久删除</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </WorkspaceShell>;
}
