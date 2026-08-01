import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, FileText, Folder, FolderOpen, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listSpaceEntries, type SpaceEntry } from "@/lib/space-api";

interface DocumentDirectoryPanelProps {
  folderID: string;
  folderName: string;
  currentDocumentID: string;
  currentDocumentName: string;
  className?: string;
  onNavigate?: () => void;
}

const entryClass =
  "flex min-h-11 min-w-0 items-center gap-3 rounded-xl border border-transparent px-3 py-2 text-sm transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function DocumentDirectoryPanel({
  folderID,
  folderName,
  currentDocumentID,
  currentDocumentName,
  className,
  onNavigate,
}: DocumentDirectoryPanelProps) {
  const [items, setItems] = useState<SpaceEntry[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listSpaceEntries(folderID, "name", 0, controller.signal, 48)
      .then((response) => {
        setItems(response.items);
        setHasMore(response.has_more);
      })
      .catch((reason: unknown) => {
        if ((reason as Error).name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : "无法读取当前文件夹");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [folderID, retry]);

  const orderedItems = useMemo(
    () => [
      ...items.filter((item) => item.kind === "folder"),
      ...items.filter((item) => item.kind === "document"),
    ],
    [items],
  );
  const currentVisible = orderedItems.some((item) => item.id === currentDocumentID);

  const renderEntry = (entry: SpaceEntry) => {
    const current = entry.id === currentDocumentID;
    const href = entry.kind === "folder" ? `/space/folders/${entry.id}` : `/space/documents/${entry.id}`;
    const Icon = entry.kind === "folder" ? Folder : FileText;
    return (
      <Link
        key={entry.id}
        to={href}
        onClick={onNavigate}
        aria-current={current ? "page" : undefined}
        title={entry.name}
        className={cn(
          entryClass,
          current
            ? "border-primary/20 bg-primary/10 font-medium text-foreground"
            : "text-muted-foreground",
        )}
      >
        <Icon className={cn("h-4 w-4 shrink-0", current ? "text-primary" : "text-muted-foreground")} aria-hidden="true" />
        <span className="truncate">{entry.name}</span>
      </Link>
    );
  };

  return (
    <aside className={cn("flex h-full min-h-0 flex-col bg-muted/20", className)} aria-label="当前文件夹">
      <div className="shrink-0 border-b bg-background/70 p-4">
        <Button asChild variant="ghost" className="-ml-3 h-11 max-w-full justify-start px-3">
          <Link to={`/space/folders/${folderID}`} onClick={onNavigate}>
            <ArrowLeft className="mr-2 h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="truncate">返回“{folderName}”</span>
          </Link>
        </Button>
        <div className="mt-3 flex min-w-0 items-center gap-3 px-1">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <FolderOpen className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">当前文件夹</p>
            <h2 className="mt-1 truncate text-sm font-semibold" title={folderName}>{folderName}</h2>
          </div>
        </div>
      </div>

      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain p-3" aria-label={`“${folderName}”中的项目`}>
        {loading && <p role="status" className="px-3 py-8 text-center text-xs text-muted-foreground">正在读取目录…</p>}
        {!loading && error && (
          <div role="alert" className="px-3 py-8 text-center">
            <p className="text-xs leading-5 text-destructive">{error}</p>
            <Button type="button" variant="ghost" size="sm" className="mt-2 min-h-11" onClick={() => setRetry((value) => value + 1)}>
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />重新加载
            </Button>
          </div>
        )}
        {!loading && !error && !currentVisible && renderEntry({
          id: currentDocumentID,
          parent_id: folderID,
          kind: "document",
          name: currentDocumentName,
          version: 1,
          created_at: "",
          updated_at: "",
        })}
        {!loading && !error && orderedItems.map(renderEntry)}
        {!loading && !error && hasMore && (
          <p className="px-3 py-3 text-xs leading-5 text-muted-foreground">这里只显示前 48 项，进入文件夹可查看完整目录。</p>
        )}
      </nav>
    </aside>
  );
}
