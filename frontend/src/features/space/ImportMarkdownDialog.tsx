import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, FolderPlus, FolderUp, Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FolderPickerDialog } from "@/features/space/FolderPickerDialog";
import {
  createFolder,
  preflightMarkdownImport,
  uploadMarkdownImport,
  type MarkdownImportManifest,
  type MarkdownImportPreview,
  type MarkdownImportResult,
  type SpaceFolder,
} from "@/lib/space-api";

type ImportMode = "folder" | "file";

interface ImportMarkdownDialogProps {
  open: boolean;
  mode: ImportMode;
  currentFolderID: string | null;
  currentFolderName: string;
  onOpenChange: (open: boolean) => void;
  onImported: (result: MarkdownImportResult) => void;
}

interface PreparedImport {
  manifest: MarkdownImportManifest;
  files: Map<string, File>;
  preview: MarkdownImportPreview;
  targetName: string;
}

const MAX_FILES = 500;
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const MAX_BATCH_BYTES = 20 * 1024 * 1024;

export function ImportMarkdownDialog({ open, mode, currentFolderID, currentFolderName, onOpenChange, onImported }: ImportMarkdownDialogProps) {
  const { csrfToken } = useAuth();
  const folderInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [activeMode, setActiveMode] = useState<ImportMode>(mode);
  const [prepared, setPrepared] = useState<PreparedImport | null>(null);
  const [result, setResult] = useState<MarkdownImportResult | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [targetPickerOpen, setTargetPickerOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);

  useEffect(() => {
    if (!open) return;
    setActiveMode(mode);
    setPrepared(null);
    setResult(null);
    setPreparing(false);
    setUploading(false);
    setProgress(0);
    setError("");
    setPendingFiles([]);
    setNewFolderName("");
  }, [mode, open]);

  useEffect(() => () => request.current?.abort(), []);

  const close = () => {
    if (uploading) return;
    request.current?.abort();
    onOpenChange(false);
  };

  const handleSelection = async (files: File[], selectedMode: ImportMode) => {
    setError("");
    setResult(null);
    setPrepared(null);
    if (files.length === 0) return;
    if (selectedMode === "file" && !currentFolderID) {
      setPendingFiles([files[0]]);
      setTargetPickerOpen(true);
      return;
    }
    await prepare(files, selectedMode, currentFolderID, currentFolderName);
  };

  const prepare = async (files: File[], selectedMode: ImportMode, targetFolderID: string | null, targetName: string) => {
    if (files.length > MAX_FILES) {
      setError(`一次最多导入 ${MAX_FILES} 个文件`);
      return;
    }
    setPreparing(true);
    setError("");
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const firstPath = selectedMode === "folder" ? files[0].webkitRelativePath.split("\\").join("/") : files[0].name;
      const rootName = selectedMode === "folder" ? firstPath.split("/")[0] : null;
      if (selectedMode === "folder" && (!rootName || files.some((file) => file.webkitRelativePath.split("\\").join("/").split("/")[0] !== rootName))) {
        throw new Error("请选择一个完整文件夹，不要混合多个根目录");
      }
      let markdownBytes = 0;
      const uploadFiles = new Map<string, File>();
      const entries: MarkdownImportManifest["entries"] = [];
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        const fullPath = selectedMode === "folder" ? file.webkitRelativePath.split("\\").join("/") : file.name;
        const relativePath = selectedMode === "folder" ? fullPath.split("/").slice(1).join("/") : file.name;
        if (!relativePath) continue;
        const supported = relativePath.toLowerCase().endsWith(".md");
        if (supported) {
          if (file.size > MAX_FILE_BYTES) throw new Error(`“${relativePath}”超过单文件 2 MB 限制`);
          markdownBytes += file.size;
          if (markdownBytes > MAX_BATCH_BYTES) throw new Error("Markdown 总大小超过单批 20 MB 限制");
        }
        const contentHash = await sha256(file);
        const uploadField = supported ? `file_${index}` : undefined;
        if (uploadField) uploadFiles.set(uploadField, file);
        entries.push({
          kind: supported ? "file" : "unsupported",
          relative_path: relativePath,
          size: file.size,
          content_hash: contentHash,
          media_type: file.type || (supported ? "text/markdown" : "application/octet-stream"),
          upload_field: uploadField,
        });
      }
      if (entries.length === 0) throw new Error("所选文件夹中没有可读取的文件");
      const manifest: MarkdownImportManifest = {
        batch_id: crypto.randomUUID(),
        target_folder_id: targetFolderID,
        root_name: rootName,
        entries,
      };
      const preview = await preflightMarkdownImport(csrfToken, manifest, controller.signal);
      setPrepared({ manifest, files: uploadFiles, preview, targetName });
    } catch (reason) {
      if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取所选内容");
    } finally {
      if (!controller.signal.aborted) setPreparing(false);
    }
  };

  const selectTarget = (folder: SpaceFolder | null) => {
    if (!folder || pendingFiles.length === 0) return;
    setTargetPickerOpen(false);
    void prepare(pendingFiles, "file", folder.id, folder.name);
    setPendingFiles([]);
  };

  const createTargetFolder = async () => {
    const name = newFolderName.trim();
    if (!name || pendingFiles.length === 0) return;
    setCreatingFolder(true);
    try {
      const folder = await createFolder(csrfToken, { parent_id: null, name });
      setTargetPickerOpen(false);
      await prepare(pendingFiles, "file", folder.id, folder.name);
      setPendingFiles([]);
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "无法创建文件夹");
    } finally {
      setCreatingFolder(false);
    }
  };

  const confirmImport = async () => {
    if (!prepared || prepared.preview.markdown_count === 0) return;
    setUploading(true);
    setProgress(0);
    setError("");
    const controller = new AbortController();
    request.current = controller;
    try {
      const imported = await uploadMarkdownImport(csrfToken, prepared.manifest.batch_id, prepared.manifest, prepared.files, setProgress, controller.signal);
      setResult(imported);
      setProgress(100);
      onImported(imported);
    } catch (reason) {
      if ((reason as Error).name === "AbortError") setError("导入已取消，没有写入不完整目录");
      else setError(reason instanceof Error ? reason.message : "导入没有完成");
    } finally {
      setUploading(false);
    }
  };

  const preview = prepared?.preview;
  const warningItems = preview?.items ?? [];

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => { if (!next) close(); }}>
        <DialogContent className="max-h-[min(46rem,90vh)] max-w-2xl overflow-hidden p-0">
          <DialogHeader className="border-b px-6 py-5">
            <DialogTitle>{result ? "导入完成" : "导入到我的空间"}</DialogTitle>
            <DialogDescription>先在本地生成安全清单并预检；确认后才上传 Markdown，其他格式只列入未导入摘要。</DialogDescription>
          </DialogHeader>

          <div className="min-h-0 overflow-y-auto px-6 py-5">
            {!prepared && !result && !preparing && (
              <div className="grid gap-3 sm:grid-cols-2">
                <button type="button" onClick={() => { setActiveMode("folder"); folderInput.current?.click(); }} className={`min-h-32 rounded-2xl border p-5 text-left transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${activeMode === "folder" ? "border-primary/35 bg-primary/5" : ""}`}>
                  <FolderUp className="h-6 w-6 text-primary" aria-hidden="true" /><span className="mt-4 block font-medium">导入文件夹</span><span className="mt-1 block text-sm text-muted-foreground">保留嵌套目录与 Markdown 文件</span>
                </button>
                <button type="button" onClick={() => { setActiveMode("file"); fileInput.current?.click(); }} className={`min-h-32 rounded-2xl border p-5 text-left transition-colors hover:border-primary/40 hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${activeMode === "file" ? "border-primary/25 bg-muted/50" : ""}`}>
                  <FileText className="h-6 w-6 text-[hsl(var(--brand-coral))]" aria-hidden="true" /><span className="mt-4 block font-medium">导入 Markdown</span><span className="mt-1 block text-sm text-muted-foreground">选择一篇 UTF-8 .md 文档</span>
                </button>
              </div>
            )}
            <input ref={folderInput} type="file" multiple className="sr-only" aria-label="选择要导入的文件夹" onChange={(event) => void handleSelection(Array.from(event.target.files ?? []), "folder")} {...({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>)} />
            <input ref={fileInput} type="file" accept=".md,text/markdown" className="sr-only" aria-label="选择要导入的 Markdown" onChange={(event) => void handleSelection(Array.from(event.target.files ?? []), "file")} />

            {preparing && <div role="status" aria-live="polite" className="grid min-h-52 place-items-center text-center"><div><Loader2 className="mx-auto h-7 w-7 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" /><p className="mt-3 text-sm text-muted-foreground">正在计算文件校验值并预检…</p></div></div>}
            {error && <div role="alert" className="mb-4 flex gap-3 rounded-xl border border-destructive/25 bg-destructive/5 p-4 text-sm text-destructive"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /><span>{error}</span></div>}

            {preview && !result && (
              <div className="space-y-5">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Summary label="Markdown" value={preview.markdown_count} />
                  <Summary label="总大小" value={formatBytes(preview.total_bytes)} />
                  <Summary label="重复 / 冲突" value={`${preview.duplicates} / ${preview.conflicts}`} />
                  <Summary label="未支持" value={preview.unsupported} />
                </div>
                <div className="rounded-xl border bg-muted/25 p-4 text-sm"><p className="font-medium">{prepared.manifest.root_name ? `文件夹：${prepared.manifest.root_name}` : `文档：${prepared.manifest.entries[0]?.relative_path}`}</p><p className="mt-1 text-muted-foreground">目标位置：{prepared.targetName}</p></div>
                {warningItems.length > 0 && <div><h3 className="mb-2 text-sm font-medium">需要留意的项目</h3><ul className="max-h-44 space-y-1 overflow-y-auto rounded-xl border p-2">{warningItems.map((item) => <li key={`${item.status}-${item.relative_path}`} className="flex min-h-10 items-center gap-3 rounded-lg px-2 text-sm"><StatusIcon status={item.status} /><span className="min-w-0 flex-1 truncate" title={item.relative_path}>{item.relative_path}</span><span className="shrink-0 text-xs text-muted-foreground">{statusLabel(item.status)}</span></li>)}</ul></div>}
                {preview.markdown_count === 0 && <p role="alert" className="text-sm text-destructive">没有可导入的 Markdown，请重新选择。</p>}
              </div>
            )}

            {uploading && <div className="space-y-3 py-8" role="status" aria-live="polite"><div className="flex items-center justify-between text-sm"><span>正在上传并建立目录…</span><span className="tabular-nums">{progress}%</span></div><div role="progressbar" aria-label="Markdown 导入进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${progress}%` }} /></div><p className="text-xs text-muted-foreground">取消后服务端不会留下半棵目录。</p></div>}

            {result && <div className="space-y-5"><div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4"><CheckCircle2 className="mt-0.5 h-5 w-5 text-primary" aria-hidden="true" /><div><p className="font-medium">目录和文档已处理</p><p className="mt-1 text-sm text-muted-foreground">新增 {result.added}，重复跳过 {result.duplicates}，冲突 {result.conflicts}，未支持 {result.unsupported}，失败 {result.failed}</p></div></div>{result.items.length > 0 && <ul className="max-h-64 space-y-1 overflow-y-auto rounded-xl border p-2">{result.items.map((item) => <li key={`${item.status}-${item.relative_path}`} className="flex min-h-10 items-center gap-3 rounded-lg px-2 text-sm"><StatusIcon status={item.status} /><span className="min-w-0 flex-1 truncate" title={item.relative_path}>{item.relative_path}</span><span className="shrink-0 text-xs text-muted-foreground">{statusLabel(item.status)}</span></li>)}</ul>}</div>}
          </div>

          <DialogFooter className="border-t px-6 py-4">
            {result ? <Button onClick={close}>查看导入内容</Button> : <><Button variant="outline" onClick={uploading ? () => request.current?.abort() : close}>{uploading ? <><X className="mr-2 h-4 w-4" aria-hidden="true" />取消上传</> : "取消"}</Button>{prepared && !uploading && <Button onClick={() => void confirmImport()} disabled={prepared.preview.markdown_count === 0}><Upload className="mr-2 h-4 w-4" aria-hidden="true" />确认导入</Button>}</>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <FolderPickerDialog open={targetPickerOpen} onOpenChange={setTargetPickerOpen} initialFolderID={null} onSelect={selectTarget} selectionVerb="导入到" description="单篇 Markdown 需要放入一个具体文件夹。" footerBefore={<div className="mr-auto flex min-w-0 items-center gap-2"><Label htmlFor="import-new-folder" className="sr-only">新建顶层文件夹</Label><Input id="import-new-folder" className="h-10 w-40" value={newFolderName} onChange={(event) => setNewFolderName(event.target.value)} placeholder="新建顶层文件夹" /><Button type="button" size="icon" variant="outline" className="h-10 w-10 shrink-0" aria-label="创建并选择此文件夹" disabled={!newFolderName.trim() || creatingFolder} onClick={() => void createTargetFolder()}><FolderPlus className="h-4 w-4" aria-hidden="true" /></Button></div>} />
    </>
  );
}

function Summary({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-xl border bg-card p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-medium tabular-nums">{value}</p></div>;
}

function StatusIcon({ status }: { status: string }) {
  return status === "conflict" || status === "failed" ? <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />;
}

function statusLabel(status: string): string {
  return ({ added: "已新增", skipped_duplicate: "重复跳过", conflict: "冲突", unsupported: "不支持", failed: "失败" } as Record<string, string>)[status] ?? status;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}
