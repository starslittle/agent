import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { RotateCcw, Search, ShieldCheck } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { RunDetail } from "@/features/runs/RunDetail";
import { RunList } from "@/features/runs/RunList";
import { RunWorkspaceShell } from "@/features/runs/RunWorkspaceShell";
import {
  getObservableRunDetail,
  listObservableRuns,
  type ObservabilityRunListQuery,
  type RunDetail as RunDetailData,
  type RunStatus,
  type RunSummary,
} from "@/lib/run-api";

const INTERNAL_BASE = "/internal/agent-runs";
const validStatuses = new Set<RunStatus>([
  "queued", "running", "cancel_requested", "completed", "cancelled", "failed", "timed_out",
]);

interface FilterDraft {
  userID: string;
  skill: string;
  workflow: string;
  model: string;
  errorCode: string;
  from: string;
  to: string;
}

const emptyDraft: FilterDraft = {
  userID: "", skill: "", workflow: "", model: "", errorCode: "", from: "", to: "",
};

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

function isoBoundary(value: string, end: boolean): string | undefined {
  if (!value) return undefined;
  const date = new Date(`${value}T${end ? "23:59:59.999" : "00:00:00"}`);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

function draftFromParams(params: URLSearchParams): FilterDraft {
  return {
    userID: params.get("user_id") || "",
    skill: params.get("skill") || "",
    workflow: params.get("workflow") || "",
    model: params.get("model") || "",
    errorCode: params.get("error_code") || "",
    from: params.get("from_date") || "",
    to: params.get("to_date") || "",
  };
}

export default function AgentObservabilityPage() {
  const { runId } = useParams<{ runId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const searchKey = searchParams.toString();
  const status = useMemo(() => {
    const raw = new URLSearchParams(searchKey).get("status") as RunStatus | null;
    return raw && validStatuses.has(raw) ? raw : "";
  }, [searchKey]);
  const [draft, setDraft] = useState<FilterDraft>(() => draftFromParams(searchParams));
  const [items, setItems] = useState<RunSummary[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState("");
  const [listRetry, setListRetry] = useState(0);
  const [detail, setDetail] = useState<RunDetailData | null>(null);
  const [detailLoading, setDetailLoading] = useState(Boolean(runId));
  const [detailError, setDetailError] = useState("");
  const [detailRetry, setDetailRetry] = useState(0);

  const activeQuery = useMemo<ObservabilityRunListQuery>(() => {
    const params = new URLSearchParams(searchKey);
    return {
      userID: params.get("user_id") || undefined,
      skill: params.get("skill") || undefined,
      workflow: params.get("workflow") || undefined,
      model: params.get("model") || undefined,
      status,
      errorCode: params.get("error_code") || undefined,
      from: isoBoundary(params.get("from_date") || "", false),
      to: isoBoundary(params.get("to_date") || "", true),
      limit: 20,
    };
  }, [searchKey, status]);

  useEffect(() => setDraft(draftFromParams(new URLSearchParams(searchKey))), [searchKey]);

  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    setListError("");
    void listObservableRuns(activeQuery, controller.signal)
      .then((response) => {
        setItems(response.items);
        setNextBefore(response.next_before ?? null);
      })
      .catch((error) => {
        if ((error as Error).name !== "AbortError") setListError(messageFrom(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setListLoading(false);
      });
    return () => controller.abort();
  }, [activeQuery, listRetry]);

  useEffect(() => {
    if (!runId) {
      setDetail(null);
      setDetailError("");
      setDetailLoading(false);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailError("");
    void getObservableRunDetail(runId, controller.signal)
      .then(setDetail)
      .catch((error) => {
        if ((error as Error).name !== "AbortError") setDetailError(messageFrom(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [detailRetry, runId]);

  const handleLoadMore = useCallback(async () => {
    if (!nextBefore || loadingMore) return;
    setLoadingMore(true);
    try {
      const response = await listObservableRuns({ ...activeQuery, before: nextBefore });
      setItems((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...current, ...response.items.filter((item) => !known.has(item.id))];
      });
      setNextBefore(response.items.length === 0 ? null : (response.next_before ?? null));
    } catch (error) {
      setListError(messageFrom(error));
    } finally {
      setLoadingMore(false);
    }
  }, [activeQuery, loadingMore, nextBefore]);

  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams();
    const values: Array<[string, string]> = [
      ["user_id", draft.userID], ["skill", draft.skill], ["workflow", draft.workflow],
      ["model", draft.model], ["error_code", draft.errorCode], ["from_date", draft.from], ["to_date", draft.to],
    ];
    values.forEach(([key, value]) => {
      if (value.trim()) next.set(key, value.trim());
    });
    if (status) next.set("status", status);
    navigate(`${INTERNAL_BASE}${next.size ? `?${next}` : ""}`);
  };

  const changeStatus = (nextStatus: RunStatus | "") => {
    const next = new URLSearchParams(searchParams);
    if (nextStatus) next.set("status", nextStatus); else next.delete("status");
    navigate(`${INTERNAL_BASE}${next.size ? `?${next}` : ""}`);
  };

  const clearFilters = () => {
    setDraft(emptyDraft);
    navigate(INTERNAL_BASE);
  };

  return (
    <RunWorkspaceShell mode="internal">
      <div className="flex h-full min-h-0 flex-col">
        <form
          onSubmit={applyFilters}
          className={`${runId ? "hidden lg:block " : ""}shrink-0 border-b border-border bg-card px-4 py-3`}
          aria-label="内部运行筛选"
        >
          <div className="flex items-center gap-2 text-xs font-semibold"><ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />只读筛选</div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            {[
              ["userID", "用户 ID", "UUID"], ["skill", "Skill", "例如 research"],
              ["workflow", "Workflow", "执行路线"], ["model", "Model", "ID 或实际模型"],
              ["errorCode", "错误码", "例如 tool_failed"],
            ].map(([key, label, placeholder]) => (
              <label key={key} className="text-[10px] font-medium text-muted-foreground">
                {label}
                <input value={draft[key as keyof FilterDraft]} onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))} placeholder={placeholder} className="mt-1 h-10 w-full rounded-lg border border-input bg-background px-3 text-xs text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary focus:ring-4 focus:ring-ring/15" />
              </label>
            ))}
            <label className="text-[10px] font-medium text-muted-foreground">开始日期<input type="date" value={draft.from} onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border border-input bg-background px-3 text-xs text-foreground outline-none focus:border-primary focus:ring-4 focus:ring-ring/15" /></label>
            <label className="text-[10px] font-medium text-muted-foreground">结束日期<input type="date" value={draft.to} onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border border-input bg-background px-3 text-xs text-foreground outline-none focus:border-primary focus:ring-4 focus:ring-ring/15" /></label>
            <div className="flex items-end gap-1">
              <button type="submit" className="inline-flex h-10 flex-1 items-center justify-center gap-1 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25"><Search className="h-3.5 w-3.5" aria-hidden="true" />筛选</button>
              <button type="button" onClick={clearFilters} className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-background text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="清除全部筛选"><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /></button>
            </div>
          </div>
        </form>

        <div className="grid min-h-0 flex-1 lg:grid-cols-[21rem_minmax(0,1fr)]">
          <div className={runId ? "hidden min-h-0 lg:block" : "min-h-0"}>
            <RunList
              items={items}
              selectedRunID={runId}
              status={status}
              loading={listLoading}
              loadingMore={loadingMore}
              hasMore={Boolean(nextBefore)}
              error={listError}
              onStatusChange={changeStatus}
              onRetry={() => setListRetry((current) => current + 1)}
              onLoadMore={() => void handleLoadMore()}
              basePath={INTERNAL_BASE}
              detailSearch={searchKey ? `?${searchKey}` : ""}
              showOwner
              showEmptyAction={false}
              emptyDescription="当前筛选条件下没有可查看的运行记录。"
            />
          </div>
          <RunDetail
            detail={detail}
            loading={detailLoading}
            error={detailError}
            onRetry={() => setDetailRetry((current) => current + 1)}
            basePath={`${INTERNAL_BASE}${searchKey ? `?${searchKey}` : ""}`}
            showConversationLink={false}
            showOwner
          />
        </div>
      </div>
    </RunWorkspaceShell>
  );
}
