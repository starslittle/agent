import { useCallback, useEffect, useMemo, useState } from "react";
import { FilePlus2, FileText, Folder, FolderPlus, MoreHorizontal, Move, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FolderPickerDialog } from "@/features/space/FolderPickerDialog";
import { createDocument, createFolder, deleteFolder, getFolder, getFolderBreadcrumbs, listSpaceEntries, updateFolder, type SpaceEntry, type SpaceFolder, type SpaceSort } from "@/lib/space-api";

type EditMode = "folder" | "document" | "rename" | null;

export default function SpacePage() {
  const { folderId } = useParams<{ folderId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { csrfToken } = useAuth();
  const sort: SpaceSort = searchParams.get("sort") === "recent" ? "recent" : "name";
  const page = Math.max(1, Number.parseInt(searchParams.get("page") || "1", 10) || 1);
  const [folder, setFolder] = useState<SpaceFolder | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<SpaceFolder[]>([]);
  const [items, setItems] = useState<SpaceEntry[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [dialog, setDialog] = useState<EditMode>(null);
  const [selected, setSelected] = useState<SpaceEntry | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SpaceFolder | null>(null);
  const [moveTarget, setMoveTarget] = useState<SpaceFolder | null>(null);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    const detail = folderId ? getFolder(folderId, signal) : Promise.resolve(null);
    const crumbs = folderId ? getFolderBreadcrumbs(folderId, signal) : Promise.resolve({ items: [] });
    return Promise.all([detail, crumbs, listSpaceEntries(folderId ?? null, sort, (page - 1) * 48, signal, 48)])
      .then(([current, path, response]) => {
        setFolder(current);
        setBreadcrumbs(path.items);
        setItems(response.items);
        setHasMore(response.has_more);
      })
      .catch((reason: unknown) => {
        if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取空间");
      })
      .finally(() => { if (!signal?.aborted) setLoading(false); });
  }, [folderId, page, sort]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, retry]);

  const pageTitle = folder?.name ?? "我的空间";
  const subtitle = folder ? "逐层整理当前文件夹" : "把启点需要了解的资料放在这里";
  const openCreate = (mode: "folder" | "document") => { setSelected(null); setName(""); setDialog(mode); };
  const openRename = (entry: SpaceEntry) => { setSelected(entry); setName(entry.name); setDialog("rename"); };

  const submitDialog = async () => {
    const cleanName = name.trim();
    if (!cleanName || busy) return;
    setBusy(true);
    try {
      if (dialog === "folder") {
        await createFolder(csrfToken, { parent_id: folderId ?? null, name: cleanName });
        toast.success("文件夹已创建");
      } else if (dialog === "document" && folderId) {
        const document = await createDocument(csrfToken, { folder_id: folderId, name: cleanName.endsWith(".md") ? cleanName : `${cleanName}.md`, content: `# ${cleanName.replace(/\.md$/i, "")}\n` });
        navigate(`/space/documents/${document.id}`);
        return;
      } else if (dialog === "rename" && selected?.kind === "folder") {
        await updateFolder(csrfToken, selected.id, { parent_id: selected.parent_id ?? null, name: cleanName, expected_version: selected.version });
        toast.success("文件夹已重命名");
      }
      setDialog(null);
      setRetry((value) => value + 1);
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "操作没有完成");
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget || busy) return;
    setBusy(true);
    try {
      await deleteFolder(csrfToken, deleteTarget);
      toast.success("空文件夹已删除");
      setDeleteTarget(null);
      setRetry((value) => value + 1);
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "删除没有完成");
    } finally { setBusy(false); }
  };

  const moveFolderTo = async (target: SpaceFolder | null) => {
    if (!moveTarget) return;
    try {
      await updateFolder(csrfToken, moveTarget.id, { parent_id: target?.id ?? null, name: moveTarget.name, expected_version: moveTarget.version });
      toast.success("文件夹已移动");
      setMoveTarget(null);
      setRetry((value) => value + 1);
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : "移动没有完成"); }
  };

  const folderItems = useMemo(() => items.filter((item) => item.kind === "folder"), [items]);
  const documentItems = useMemo(() => items.filter((item) => item.kind === "document"), [items]);

  return (
    <WorkspaceShell title={pageTitle} subtitle={subtitle} mainId="space-main" mainClassName="overflow-y-auto">
      <div className="mx-auto w-full max-w-[92rem] px-4 py-6 sm:px-7 lg:px-10 lg:py-9">
        <nav aria-label="当前位置" className="mb-7 flex min-w-0 items-center gap-2 overflow-x-auto pb-1 text-sm text-muted-foreground">
          <Link to={`/space?sort=${sort}`} className="shrink-0 rounded-md hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">我的空间</Link>
          {breadcrumbs.map((item) => <span key={item.id} className="flex shrink-0 items-center gap-2"><span aria-hidden="true">/</span><Link to={`/space/folders/${item.id}?sort=${sort}`} aria-current={item.id === folderId ? "page" : undefined} className="max-w-52 truncate rounded-md text-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{item.name}</Link></span>)}
        </nav>

        <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary">{folder ? "当前文件夹" : "文档桌面"}</p>
            <h2 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{pageTitle}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{folder ? `${items.length} 个项目，只展示这一层` : `${folderItems.length} 个顶层文件夹`}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={sort} onValueChange={(value: SpaceSort) => setSearchParams(value === "name" ? {} : { sort: value })}>
              <SelectTrigger className="h-11 w-40" aria-label="文档排序"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="name">名称 A–Z</SelectItem><SelectItem value="recent">最近打开</SelectItem></SelectContent>
            </Select>
            <Button variant="outline" size="icon" className="h-11 w-11" aria-label="刷新当前文件夹" onClick={() => setRetry((value) => value + 1)}><RefreshCw className="h-4 w-4" aria-hidden="true" /></Button>
            <Button variant="outline" className="h-11" onClick={() => openCreate("folder")}><FolderPlus className="mr-2 h-4 w-4" aria-hidden="true" />新建文件夹</Button>
            {folderId && <Button className="h-11" onClick={() => openCreate("document")}><FilePlus2 className="mr-2 h-4 w-4" aria-hidden="true" />新建文档</Button>}
          </div>
        </div>

        {loading && <div role="status" aria-live="polite" className="grid min-h-64 place-items-center rounded-2xl border border-dashed"><p className="text-sm text-muted-foreground">正在整理这一层…</p></div>}
        {!loading && error && <div role="alert" className="grid min-h-64 place-items-center rounded-2xl border border-destructive/30 bg-destructive/5 px-5 text-center"><div><p className="text-sm text-destructive">{error}</p><Button variant="outline" className="mt-4" onClick={() => setRetry((value) => value + 1)}>重新加载</Button></div></div>}
        {!loading && !error && items.length === 0 && <div className="grid min-h-72 place-items-center rounded-2xl border border-dashed bg-card/50 px-5 text-center"><div><Folder className="mx-auto h-9 w-9 text-primary/70" aria-hidden="true" /><h3 className="mt-4 font-medium">{folder ? "这个文件夹还是空的" : "从一个文件夹开始"}</h3><p className="mt-2 text-sm text-muted-foreground">{folder ? "创建子文件夹或 Markdown 文档。" : "按项目、目标或生活领域建立顶层分类。"}</p><Button className="mt-5" onClick={() => openCreate("folder")}><FolderPlus className="mr-2 h-4 w-4" aria-hidden="true" />新建文件夹</Button></div></div>}
        {!loading && !error && items.length > 0 && (
          <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {[...folderItems, ...documentItems].map((entry) => {
              const href = entry.kind === "folder" ? `/space/folders/${entry.id}?sort=${sort}` : `/space/documents/${entry.id}`;
              return <article key={entry.id} className="group relative flex min-w-0 items-center gap-4 rounded-2xl border bg-card p-4 transition-[border-color,box-shadow,transform] hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-sm motion-reduce:transform-none">
                <Link to={href} title={entry.name} className="absolute inset-0 rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`打开${entry.kind === "folder" ? "文件夹" : "文档"}“${entry.name}”`} />
                <span className={entry.kind === "folder" ? "grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary" : "grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[hsl(var(--brand-coral)/0.12)] text-[hsl(var(--brand-coral))]"}>{entry.kind === "folder" ? <Folder className="h-5 w-5" aria-hidden="true" /> : <FileText className="h-5 w-5" aria-hidden="true" />}</span>
                <div className="min-w-0 flex-1"><h3 className="truncate text-sm font-medium">{entry.name}</h3><p className="mt-1 truncate text-xs text-muted-foreground">{entry.kind === "folder" ? "文件夹" : "Markdown 文档"} · {new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }).format(new Date(entry.updated_at))}</p></div>
                {entry.kind === "folder" && <DropdownMenu><DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon" className="relative z-10 h-11 w-11 shrink-0" aria-label={`管理文件夹“${entry.name}”`}><MoreHorizontal className="h-4 w-4" aria-hidden="true" /></Button></DropdownMenuTrigger><DropdownMenuContent align="end"><DropdownMenuItem onSelect={() => openRename(entry)}><Pencil className="mr-2 h-4 w-4" aria-hidden="true" />重命名</DropdownMenuItem><DropdownMenuItem onSelect={() => setMoveTarget(entry as SpaceFolder)}><Move className="mr-2 h-4 w-4" aria-hidden="true" />移动到…</DropdownMenuItem><DropdownMenuSeparator /><DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDeleteTarget(entry as SpaceFolder)}><Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />删除空文件夹</DropdownMenuItem></DropdownMenuContent></DropdownMenu>}
              </article>;
            })}
          </div>
          {(page > 1 || hasMore) && <nav aria-label="文件夹分页" className="mt-7 flex items-center justify-center gap-3"><Button variant="outline" disabled={page <= 1} onClick={() => { const next = new URLSearchParams(searchParams); next.set("page", String(page - 1)); setSearchParams(next); }}>上一页</Button><span className="text-xs tabular-nums text-muted-foreground">第 {page} 页</span><Button variant="outline" disabled={!hasMore} onClick={() => { const next = new URLSearchParams(searchParams); next.set("page", String(page + 1)); setSearchParams(next); }}>下一页</Button></nav>}
          </>
        )}
      </div>

      <Dialog open={dialog !== null} onOpenChange={(open) => { if (!open && !busy) setDialog(null); }}>
        <DialogContent><DialogHeader><DialogTitle>{dialog === "folder" ? "新建文件夹" : dialog === "document" ? "新建 Markdown 文档" : "重命名文件夹"}</DialogTitle><DialogDescription>{dialog === "document" ? "文档会保存在当前文件夹，并从第一版开始保留修改历史。" : "同一层级不能出现同名文件夹或文档。"}</DialogDescription></DialogHeader><div className="space-y-2 py-2"><Label htmlFor="space-entry-name">名称</Label><Input id="space-entry-name" name="space-entry-name" autoComplete="off" value={name} onChange={(event) => setName(event.target.value)} placeholder={dialog === "document" ? "例如：2026 秋招目标…" : "例如：求职…"} onKeyDown={(event) => { if (event.key === "Enter") void submitDialog(); }} /></div><DialogFooter><Button variant="outline" onClick={() => setDialog(null)} disabled={busy}>取消</Button><Button onClick={() => void submitDialog()} disabled={!name.trim() || busy}>{busy ? "正在保存…" : dialog === "rename" ? "保存名称" : "创建"}</Button></DialogFooter></DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>删除空文件夹“{deleteTarget?.name}”？</AlertDialogTitle><AlertDialogDescription>只有空文件夹可以删除。此操作不能撤销。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => void confirmDelete()}>删除文件夹</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
      <FolderPickerDialog open={Boolean(moveTarget)} onOpenChange={(open) => { if (!open) setMoveTarget(null); }} initialFolderID={moveTarget?.parent_id ?? null} excludedFolderID={moveTarget?.id} allowRoot onSelect={(target) => void moveFolderTo(target)} />
    </WorkspaceShell>
  );
}
