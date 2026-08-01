import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, Folder, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getFolderBreadcrumbs, listSpaceEntries, type SpaceEntry, type SpaceFolder } from "@/lib/space-api";

interface FolderPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialFolderID?: string | null;
  excludedFolderID?: string;
  onSelect: (folder: SpaceFolder | null) => void;
  allowRoot?: boolean;
  selectionVerb?: string;
  description?: string;
  footerBefore?: ReactNode;
}

export function FolderPickerDialog({ open, onOpenChange, initialFolderID = null, excludedFolderID, onSelect, allowRoot = false, selectionVerb = "移动到", description = "逐层进入文件夹，再确认移动位置。", footerBefore }: FolderPickerDialogProps) {
  const [folderID, setFolderID] = useState<string | null>(initialFolderID);
  const [folders, setFolders] = useState<SpaceFolder[]>([]);
  const [breadcrumbs, setBreadcrumbs] = useState<SpaceFolder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setFolderID(initialFolderID);
  }, [initialFolderID, open]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const entries = listSpaceEntries(folderID, "name", 0, controller.signal, 50);
    const crumbs = folderID ? getFolderBreadcrumbs(folderID, controller.signal) : Promise.resolve({ items: [] });
    void Promise.all([entries, crumbs])
      .then(([result, path]) => {
        setFolders(result.items.filter((item): item is SpaceFolder => item.kind === "folder" && item.id !== excludedFolderID));
        setBreadcrumbs(path.items);
      })
      .catch((reason: unknown) => {
        if ((reason as Error).name !== "AbortError") setError(reason instanceof Error ? reason.message : "无法读取文件夹");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [excludedFolderID, folderID, open]);

  const current = breadcrumbs.at(-1) ?? null;
  const parentID = breadcrumbs.length > 1 ? breadcrumbs.at(-2)?.id ?? null : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-5">
          <DialogTitle>选择目标文件夹</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="flex min-h-72 flex-col px-4 py-3">
          <div className="flex items-center gap-1 border-b pb-3 text-xs text-muted-foreground">
            <Button type="button" variant="ghost" size="sm" className="h-9 px-2" onClick={() => setFolderID(parentID)} disabled={!folderID}>
              <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />上一级
            </Button>
            <span className="min-w-0 truncate">我的空间{breadcrumbs.map((item) => ` / ${item.name}`).join("")}</span>
          </div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain py-3">
            {loading && <p role="status" className="px-3 py-8 text-center text-sm text-muted-foreground">正在读取文件夹…</p>}
            {!loading && error && <p role="alert" className="px-3 py-8 text-center text-sm text-destructive">{error}</p>}
            {!loading && !error && folders.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted-foreground">这里没有子文件夹</p>}
            {!loading && !error && folders.map((folder) => (
              <button key={folder.id} type="button" onClick={() => setFolderID(folder.id)} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <Folder className="h-4 w-4 text-primary" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{folder.name}</span>
              </button>
            ))}
          </div>
        </div>
        <DialogFooter className="border-t px-6 py-4">
          {footerBefore}
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button type="button" onClick={() => { onSelect(current); onOpenChange(false); }} disabled={!allowRoot && !current}>
            {current ? `${selectionVerb}“${current.name}”` : <><Home className="mr-2 h-4 w-4" aria-hidden="true" />{selectionVerb}根目录</>}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
