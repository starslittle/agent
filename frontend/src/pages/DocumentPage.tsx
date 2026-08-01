import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, BrainCircuit, Clock3, Edit3, FileClock, FolderTree, MoreHorizontal, Move, Pencil, Save, Trash2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DocumentDirectoryPanel } from "@/features/space/DocumentDirectoryPanel";
import { FolderPickerDialog } from "@/features/space/FolderPickerDialog";
import { presentMarkdownDocument, safeMarkdownURL } from "@/features/space/markdown";
import { DocumentContextPanel } from "@/features/wiki/DocumentContextPanel";
import { deleteDocument, getDocument, getFolderBreadcrumbs, listDocumentRevisions, moveDocument, updateDocument, type DocumentRevision, type MarkdownDocument, type SpaceFolder } from "@/lib/space-api";

export default function DocumentPage() {
  const { documentId = "" } = useParams<{ documentId: string }>();
  const { csrfToken } = useAuth();
  const navigate = useNavigate();
  const [document, setDocument] = useState<MarkdownDocument | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<SpaceFolder[]>([]);
  const [revisions, setRevisions] = useState<DocumentRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [nextName, setNextName] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [directoryOpen, setDirectoryOpen] = useState(false);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true); setError("");
    return getDocument(documentId, signal)
      .then(async (item) => {
        const [path, history] = await Promise.all([getFolderBreadcrumbs(item.parent_id as string, signal), listDocumentRevisions(item.id, signal)]);
        setDocument(item); setDraft(item.content); setBreadcrumbs(path.items); setRevisions(history.items);
      })
      .catch((reason: unknown) => { if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取文档"); })
      .finally(() => { if (!signal?.aborted) setLoading(false); });
  }, [documentId]);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load, retry]);
  const dirty = Boolean(document && draft !== document.content);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    const guardLinks = (event: MouseEvent) => {
      if (!dirty || event.defaultPrevented || event.button !== 0) return;
      const target = event.target as Element | null;
      const link = target?.closest("a[href]");
      if (link && !window.confirm("文档有未保存的修改。确定离开并放弃这些修改吗？")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.document.addEventListener("click", guardLinks, true);
    return () => window.document.removeEventListener("click", guardLinks, true);
  }, [dirty]);

  const save = async () => {
    if (!document || !dirty || saving) return;
    setSaving(true);
    try { const updated = await updateDocument(csrfToken, document.id, draft, document.version); setDocument(updated); setDraft(updated.content); setEditing(false); toast.success("文档已保存为新版本"); setRetry((value) => value + 1); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "保存没有完成"); }
    finally { setSaving(false); }
  };

  const moveTo = async (target: SpaceFolder | null) => {
    if (!document || !target) return;
    try { const moved = await moveDocument(csrfToken, document.id, { parent_id: target.id, name: document.name, expected_version: document.version }); setDocument(moved); toast.success("文档已移动"); setRetry((value) => value + 1); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "移动没有完成"); }
  };
  const rename = async () => {
    if (!document || !document.parent_id || !nextName.trim() || saving) return;
    setSaving(true);
    try {
      const name = nextName.trim().endsWith(".md") ? nextName.trim() : `${nextName.trim()}.md`;
      const renamed = await moveDocument(csrfToken, document.id, { parent_id: document.parent_id, name, expected_version: document.version });
      setDocument(renamed); setRenameOpen(false); toast.success("文档已重命名");
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : "重命名没有完成"); }
    finally { setSaving(false); }
  };

  const remove = async () => {
    if (!document) return;
    try { await deleteDocument(csrfToken, document); toast.success("文档已永久删除"); navigate(`/space/folders/${document.parent_id}`); }
    catch (reason) { toast.error(reason instanceof Error ? reason.message : "删除没有完成"); }
  };

  const presentation = useMemo(
    () => presentMarkdownDocument(document?.content ?? "", document?.name.replace(/\.md$/i, "") || "文档"),
    [document?.content, document?.name],
  );
  const parentFolder = breadcrumbs[breadcrumbs.length - 1] ?? null;
  const parentHref = parentFolder ? `/space/folders/${parentFolder.id}` : "/space";
  const parentLabel = parentFolder?.name ?? "我的空间";
  return (
    <WorkspaceShell title={document?.name ?? "文档"} subtitle="阅读、编辑并管理关联上下文" mainId="document-main" headerActions={<>
      <Sheet open={directoryOpen} onOpenChange={setDirectoryOpen}>
        <SheetTrigger asChild><Button variant="outline" size="icon" className="h-11 w-11 xl:hidden" aria-label="打开空间目录"><FolderTree className="h-4 w-4" aria-hidden="true" /></Button></SheetTrigger>
        <SheetContent side="left" className="w-[min(92vw,20rem)] p-0"><SheetHeader className="sr-only"><SheetTitle>空间目录</SheetTitle></SheetHeader>{document && <DocumentDirectoryPanel breadcrumbs={breadcrumbs} currentDocumentID={document.id} currentDocumentName={document.name} onNavigate={() => setDirectoryOpen(false)} />}</SheetContent>
      </Sheet>
      <Sheet>
        <SheetTrigger asChild><Button variant="outline" size="icon" className="h-11 w-11" aria-label="打开关联上下文"><BrainCircuit className="h-4 w-4" aria-hidden="true" /></Button></SheetTrigger>
        <SheetContent className="w-[min(92vw,24rem)] p-0"><SheetHeader className="sr-only"><SheetTitle>关联上下文</SheetTitle></SheetHeader>{document && <DocumentContextPanel documentID={document.id} documentRevisionID={document.current_revision_id} />}</SheetContent>
      </Sheet>
    </>}>
      <div className="grid h-full min-h-0 xl:grid-cols-[18rem_minmax(0,1fr)]">
        {document && <DocumentDirectoryPanel className="hidden border-r xl:flex" breadcrumbs={breadcrumbs} currentDocumentID={document.id} currentDocumentName={document.name} />}
        <section className="min-h-0 overflow-y-auto">
          {loading && <div role="status" className="grid min-h-full place-items-center text-sm text-muted-foreground">正在打开文档…</div>}
          {!loading && error && <div role="alert" className="grid min-h-full place-items-center px-5 text-center"><div><p className="text-sm text-destructive">{error}</p><Button variant="outline" className="mt-4" onClick={() => setRetry((value) => value + 1)}>重新加载</Button></div></div>}
          {!loading && document && <div className="mx-auto w-full max-w-4xl px-4 py-6 sm:px-8 lg:px-12 lg:py-10">
            <Button asChild variant="ghost" className="-ml-3 mb-5 h-11 max-w-full justify-start px-3 xl:hidden">
              <Link to={parentHref}><ArrowLeft className="mr-2 h-4 w-4 shrink-0" aria-hidden="true" /><span className="truncate">返回“{parentLabel}”</span></Link>
            </Button>
            <nav aria-label="文档位置" className="mb-7 flex items-center gap-2 overflow-x-auto pb-1 text-xs text-muted-foreground"><Link to="/space" className="shrink-0 rounded hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">我的空间</Link>{breadcrumbs.map((item) => <span key={item.id} className="flex shrink-0 items-center gap-2"><span aria-hidden="true">/</span><Link to={`/space/folders/${item.id}`} className="max-w-40 truncate rounded hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{item.name}</Link></span>)}<span aria-hidden="true">/</span><span className="max-w-52 truncate text-foreground" aria-current="page">{document.name}</span></nav>
            <div className="mb-9 flex flex-col justify-between gap-5 border-b pb-8 sm:flex-row sm:items-start"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Markdown · 第 {document.revision_number} 版</p><h2 className="mt-3 text-balance break-words text-3xl font-semibold tracking-tight sm:text-4xl">{presentation.title}</h2><p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(document.updated_at))} 更新 · <span className="truncate" title={document.name}>{document.name}</span></p></div><div className="flex shrink-0 items-center gap-2">{editing ? <><Button variant="outline" onClick={() => { setDraft(document.content); setEditing(false); }}><X className="mr-2 h-4 w-4" aria-hidden="true" />取消</Button><Button onClick={() => void save()} disabled={!dirty || saving}><Save className="mr-2 h-4 w-4" aria-hidden="true" />{saving ? "正在保存…" : "保存新版本"}</Button></> : <Button onClick={() => setEditing(true)}><Edit3 className="mr-2 h-4 w-4" aria-hidden="true" />编辑</Button>}<DropdownMenu><DropdownMenuTrigger asChild><Button variant="outline" size="icon" className="h-11 w-11" aria-label="管理文档"><MoreHorizontal className="h-4 w-4" aria-hidden="true" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => { setNextName(document.name); setRenameOpen(true); }}><Pencil className="mr-2 h-4 w-4" aria-hidden="true" />重命名</DropdownMenuItem><DropdownMenuItem onSelect={() => setRevisionOpen(true)}><FileClock className="mr-2 h-4 w-4" aria-hidden="true" />版本历史</DropdownMenuItem><DropdownMenuItem onSelect={() => setMoveOpen(true)}><Move className="mr-2 h-4 w-4" aria-hidden="true" />移动到…</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDeleteOpen(true)}><Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />永久删除</DropdownMenuItem></DropdownMenuContent></DropdownMenu></div></div>
            {editing ? <div><label htmlFor="markdown-editor" className="sr-only">Markdown 内容</label><Textarea id="markdown-editor" name="markdown-editor" value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck className="min-h-[60vh] resize-y font-mono text-sm leading-7" /><p aria-live="polite" className="mt-2 text-xs text-muted-foreground">{dirty ? "有未保存的修改" : "内容已保存"}</p></div> : <article className="markdown-document"><ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={safeMarkdownURL}>{presentation.body}</ReactMarkdown></article>}
          </div>}
        </section>
      </div>

      <Sheet open={revisionOpen} onOpenChange={setRevisionOpen}><SheetContent className="w-[min(92vw,28rem)] overflow-y-auto overscroll-contain"><SheetHeader><SheetTitle>版本历史</SheetTitle></SheetHeader><div className="mt-6 space-y-3">{revisions.map((revision) => <article key={revision.id} className="rounded-xl border p-4"><p className="text-sm font-medium">第 {revision.revision_number} 版</p><p className="mt-1 text-xs text-muted-foreground">{new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(revision.created_at))}</p><p className="mt-3 line-clamp-4 whitespace-pre-wrap text-xs leading-5 text-muted-foreground">{revision.content}</p></article>)}</div></SheetContent></Sheet>
      <FolderPickerDialog open={moveOpen} onOpenChange={setMoveOpen} initialFolderID={document?.parent_id ?? null} onSelect={(target) => void moveTo(target)} />
      <Dialog open={renameOpen} onOpenChange={setRenameOpen}><DialogContent><DialogHeader><DialogTitle>重命名文档</DialogTitle><DialogDescription>同一文件夹中不能出现同名项目。</DialogDescription></DialogHeader><div className="space-y-2 py-2"><Label htmlFor="document-name">文档名称</Label><Input id="document-name" name="document-name" autoComplete="off" value={nextName} onChange={(event) => setNextName(event.target.value)} placeholder="例如：2026 秋招目标.md…" onKeyDown={(event) => { if (event.key === "Enter") void rename(); }} /></div><DialogFooter><Button variant="outline" onClick={() => setRenameOpen(false)}>取消</Button><Button onClick={() => void rename()} disabled={!nextName.trim() || saving}>{saving ? "正在保存…" : "保存名称"}</Button></DialogFooter></DialogContent></Dialog>
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>永久删除“{document?.name}”？</AlertDialogTitle><AlertDialogDescription>文档正文和版本历史会被删除。已经独立确认的关联上下文会保留，但不再链接原文。此操作不能撤销。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => void remove()}>永久删除文档</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    </WorkspaceShell>
  );
}
