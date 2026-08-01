import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, FileText, Folder, FolderOpen, FolderTree, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listSpaceEntries, type SpaceEntry, type SpaceFolder } from "@/lib/space-api";

interface DocumentDirectoryPanelProps {
  breadcrumbs: SpaceFolder[];
  currentDocumentID: string;
  currentDocumentName: string;
  className?: string;
  onNavigate?: () => void;
}

interface DirectoryBranch {
  items: SpaceEntry[];
  loaded: boolean;
  loading: boolean;
  hasMore: boolean;
  error: string;
}

const ROOT_KEY = "__space_root__";
const PAGE_SIZE = 200;
const emptyBranch: DirectoryBranch = {
  items: [],
  loaded: false,
  loading: false,
  hasMore: false,
  error: "",
};

function branchKey(parentID: string | null) {
  return parentID ?? ROOT_KEY;
}

function orderEntries(items: SpaceEntry[]) {
  return [
    ...items.filter((item) => item.kind === "folder"),
    ...items.filter((item) => item.kind === "document"),
  ];
}

export function DocumentDirectoryPanel({
  breadcrumbs,
  currentDocumentID,
  currentDocumentName,
  className,
  onNavigate,
}: DocumentDirectoryPanelProps) {
  const [branches, setBranches] = useState<Record<string, DirectoryBranch>>({});
  const branchesRef = useRef<Record<string, DirectoryBranch>>({});
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const controllersRef = useRef<Map<string, AbortController>>(new Map());

  const updateBranch = useCallback((key: string, update: (current: DirectoryBranch) => DirectoryBranch) => {
    setBranches((current) => {
      const next = { ...current, [key]: update(current[key] ?? emptyBranch) };
      branchesRef.current = next;
      return next;
    });
  }, []);

  const loadBranch = useCallback(async (parentID: string | null, append = false, force = false) => {
    const key = branchKey(parentID);
    const current = branchesRef.current[key];
    if (current?.loading || (!append && !force && current?.loaded)) return;

    controllersRef.current.get(key)?.abort();
    const controller = new AbortController();
    controllersRef.current.set(key, controller);
    const offset = append ? current?.items.length ?? 0 : 0;
    updateBranch(key, (branch) => ({ ...branch, loading: true, error: "" }));

    try {
      const response = await listSpaceEntries(parentID, "name", offset, controller.signal, PAGE_SIZE);
      updateBranch(key, (branch) => ({
        items: append ? [...branch.items, ...response.items] : response.items,
        loaded: true,
        loading: false,
        hasMore: response.has_more,
        error: "",
      }));
    } catch (reason: unknown) {
      if ((reason as Error).name !== "AbortError") {
        updateBranch(key, (branch) => ({
          ...branch,
          loading: false,
          error: reason instanceof Error ? reason.message : "无法读取空间目录",
        }));
      }
    } finally {
      if (controllersRef.current.get(key) === controller) controllersRef.current.delete(key);
    }
  }, [updateBranch]);

  const breadcrumbKey = useMemo(() => breadcrumbs.map((item) => item.id).join("/"), [breadcrumbs]);
  useEffect(() => {
    const pathIDs = breadcrumbs.map((item) => item.id);
    setExpandedFolders((current) => {
      const next = new Set(current);
      pathIDs.forEach((id) => next.add(id));
      return next;
    });
    void loadBranch(null);
    pathIDs.forEach((id) => void loadBranch(id));
  }, [breadcrumbKey, breadcrumbs, loadBranch]);

  useEffect(() => () => {
    controllersRef.current.forEach((controller) => controller.abort());
    controllersRef.current.clear();
  }, []);

  const currentFolderID = breadcrumbs[breadcrumbs.length - 1]?.id ?? null;

  const toggleFolder = (folderID: string) => {
    const opening = !expandedFolders.has(folderID);
    setExpandedFolders((current) => {
      const next = new Set(current);
      if (opening) next.add(folderID);
      else next.delete(folderID);
      return next;
    });
    if (opening) void loadBranch(folderID);
  };

  const renderBranch = (parentID: string | null, depth = 0): React.ReactNode => {
    const key = branchKey(parentID);
    const branch = branches[key] ?? emptyBranch;
    const orderedItems = orderEntries(branch.items);
    const currentVisible = orderedItems.some((item) => item.id === currentDocumentID);
    const visibleItems = parentID === currentFolderID && !currentVisible
      ? [...orderedItems, {
        id: currentDocumentID,
        parent_id: currentFolderID,
        kind: "document" as const,
        name: currentDocumentName,
        version: 1,
        created_at: "",
        updated_at: "",
      }]
      : orderedItems;
    const inset = Math.min(12 + depth * 16, 76);

    return (
      <>
        {visibleItems.map((entry) => {
          if (entry.kind === "folder") {
            const expanded = expandedFolders.has(entry.id);
            return (
              <div key={entry.id}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  title={entry.name}
                  onClick={() => toggleFolder(entry.id)}
                  className="flex min-h-11 w-full min-w-0 touch-manipulation items-center gap-2 rounded-lg py-2 pr-3 text-left text-sm text-muted-foreground transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  style={{ paddingLeft: inset }}
                >
                  <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 transition-transform motion-reduce:transition-none", expanded && "rotate-90")} aria-hidden="true" />
                  {expanded
                    ? <FolderOpen className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    : <Folder className="h-4 w-4 shrink-0" aria-hidden="true" />}
                  <span className="truncate font-medium">{entry.name}</span>
                </button>
                {expanded && (
                  <div>
                    {renderBranch(entry.id, depth + 1)}
                  </div>
                )}
              </div>
            );
          }

          const current = entry.id === currentDocumentID;
          return (
            <Link
              key={entry.id}
              to={`/space/documents/${entry.id}`}
              onClick={onNavigate}
              aria-current={current ? "page" : undefined}
              title={entry.name}
              className={cn(
                "flex min-h-11 min-w-0 touch-manipulation items-center gap-2 rounded-lg py-2 pr-3 text-sm transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                current
                  ? "border border-primary/20 bg-primary/10 font-medium text-foreground"
                  : "border border-transparent text-muted-foreground",
              )}
              style={{ paddingLeft: inset + 22 }}
            >
              <FileText className={cn("h-4 w-4 shrink-0", current && "text-primary")} aria-hidden="true" />
              <span className="truncate">{entry.name}</span>
            </Link>
          );
        })}

        {branch.loading && (
          <p role="status" className="py-3 pr-3 text-xs text-muted-foreground" style={{ paddingLeft: inset + 22 }}>
            正在读取…
          </p>
        )}
        {!branch.loading && branch.error && (
          <div role="alert" className="py-2 pr-3" style={{ paddingLeft: inset + 22 }}>
            <p className="text-xs leading-5 text-destructive">{branch.error}</p>
            <Button type="button" variant="ghost" size="sm" className="mt-1 min-h-11" onClick={() => void loadBranch(parentID, false, true)}>
              <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />重新加载
            </Button>
          </div>
        )}
        {branch.loaded && !branch.loading && !branch.error && visibleItems.length === 0 && parentID !== null && (
          <p className="py-2 pr-3 text-xs text-muted-foreground" style={{ paddingLeft: inset + 22 }}>空文件夹</p>
        )}
        {branch.loaded && !branch.loading && !branch.error && branch.hasMore && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11 justify-start text-xs text-primary"
            style={{ marginLeft: inset + 14 }}
            onClick={() => void loadBranch(parentID, true)}
          >
            加载更多
          </Button>
        )}
      </>
    );
  };

  return (
    <aside className={cn("flex h-full min-h-0 flex-col bg-muted/20", className)} aria-label="空间目录">
      <div className="shrink-0 border-b bg-background/70 p-4">
        <Link
          to="/space"
          onClick={onNavigate}
          className="flex min-h-11 min-w-0 touch-manipulation items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <FolderTree className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold text-foreground">我的空间</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">展开文件夹，直接切换文档</span>
          </span>
        </Link>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3" aria-label="我的空间全部文件">
        {renderBranch(null)}
      </nav>
    </aside>
  );
}
