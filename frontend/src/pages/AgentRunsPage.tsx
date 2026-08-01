import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { RunDetail } from "@/features/runs/RunDetail";
import { RunList } from "@/features/runs/RunList";
import { RunWorkspaceShell } from "@/features/runs/RunWorkspaceShell";
import {
  getRunDetail,
  listRuns,
  type RunDetail as RunDetailData,
  type RunStatus,
  type RunSummary,
} from "@/lib/run-api";

const validStatuses = new Set<RunStatus>([
  "queued",
  "running",
  "cancel_requested",
  "completed",
  "cancelled",
  "failed",
  "timed_out",
]);

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

export default function AgentRunsPage() {
  const { runId } = useParams<{ runId?: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const status = useMemo(() => {
    const raw = searchParams.get("status") as RunStatus | null;
    return raw && validStatuses.has(raw) ? raw : "";
  }, [searchParams]);

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

  useEffect(() => {
    const controller = new AbortController();
    setListLoading(true);
    setListError("");
    void listRuns({ status, limit: 20 }, controller.signal)
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
  }, [listRetry, status]);

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
    void getRunDetail(runId, controller.signal)
      .then(setDetail)
      .catch((error) => {
        if ((error as Error).name !== "AbortError") setDetailError(messageFrom(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [detailRetry, runId]);

  useEffect(() => {
    if (!runId || !detail || !["queued", "running", "cancel_requested"].includes(detail.run.status)) return;
    const timer = window.setInterval(() => {
      void getRunDetail(runId)
        .then((next) => {
          setDetail(next);
          setItems((current) => current.map((item) => item.id === next.run.id ? next.run : item));
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [detail, runId]);

  const handleLoadMore = useCallback(async () => {
    if (!nextBefore || loadingMore) return;
    setLoadingMore(true);
    try {
      const response = await listRuns({ status, before: nextBefore, limit: 20 });
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
  }, [loadingMore, nextBefore, status]);

  const handleStatusChange = useCallback((nextStatus: RunStatus | "") => {
    const search = nextStatus ? `?status=${nextStatus}` : "";
    navigate(`/agent-runs${search}`);
  }, [navigate]);

  return (
    <RunWorkspaceShell>
      <div className="grid h-full min-h-0 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <div className={runId ? "hidden h-full min-h-0 lg:block" : "h-full min-h-0"}>
          <RunList
            items={items}
            selectedRunID={runId}
            status={status}
            loading={listLoading}
            loadingMore={loadingMore}
            hasMore={Boolean(nextBefore)}
            error={listError}
            onStatusChange={handleStatusChange}
            onRetry={() => setListRetry((current) => current + 1)}
            onLoadMore={() => void handleLoadMore()}
          />
        </div>
        <RunDetail
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onRetry={() => setDetailRetry((current) => current + 1)}
        />
      </div>
    </RunWorkspaceShell>
  );
}
