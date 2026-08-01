import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Bot,
  Clock3,
  FileText,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Wrench,
} from "lucide-react";

import type { RunDetail as RunDetailData, RunEvent, RunSpan } from "@/lib/run-api";
import { getVisibleSkill, skillSourceLabel, type SkillSelectionSource } from "@/features/skills/skills";
import { useSkillCatalog } from "@/features/skills/skill-catalog-context";
import { RunStatusBadge } from "./RunStatusBadge";
import {
  eventLabel,
  formatDuration,
  formatRunTime,
  safeArtifact,
  safeCitation,
  stableRunEvents,
} from "./run-presentation";

interface RunDetailProps {
  detail: RunDetailData | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  basePath?: string;
  showConversationLink?: boolean;
  showOwner?: boolean;
}

const numberFormatter = new Intl.NumberFormat("zh-CN");

function timelineTone(event: RunEvent): string {
  if (event.type.includes("failed")) return "bg-destructive";
  if (event.type.includes("timed_out")) return "bg-amber-500";
  if (event.type.includes("cancel")) return "bg-muted-foreground";
  if (event.type.includes("completed")) return "bg-primary";
  return "bg-background border-2 border-primary";
}

function capabilitySpans(spans: RunSpan[]): RunSpan[] {
  return spans
    .filter((span) => ["tool", "capability", "retrieval"].includes(span.type))
    .sort((left, right) => left.started_at.localeCompare(right.started_at) || left.span_id.localeCompare(right.span_id));
}

function Definition({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{term}</dt>
      <dd className="mt-1 break-words text-xs text-foreground">{children || "—"}</dd>
    </div>
  );
}

export function RunDetail({
  detail,
  loading,
  error,
  onRetry,
  basePath = "/agent-runs",
  showConversationLink = true,
  showOwner = false,
}: RunDetailProps) {
  const { skills } = useSkillCatalog();
  if (loading) {
    return (
      <section className="flex min-h-0 flex-1 items-center justify-center gap-2 bg-background text-xs text-muted-foreground" aria-label="运行详情加载中">
        <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        正在读取运行详情
      </section>
    );
  }

  if (error) {
    return (
      <section className="flex min-h-0 flex-1 items-center justify-center bg-background p-6" aria-label="运行详情错误">
        <div className="max-w-md rounded-2xl border border-destructive/25 bg-destructive/5 p-5">
          <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
          <h2 className="mt-3 text-sm font-semibold">运行详情暂时无法加载</h2>
          <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">{error}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={onRetry} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-xs font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25">
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />重试
            </button>
            <Link to={basePath} className="inline-flex min-h-11 items-center rounded-xl border border-border bg-background px-4 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">返回列表</Link>
          </div>
        </div>
      </section>
    );
  }

  if (!detail) {
    return (
      <section className="hidden min-h-0 flex-1 items-center justify-center bg-background p-8 text-center lg:flex" aria-label="未选择运行">
        <div className="max-w-sm">
          <Clock3 className="mx-auto h-8 w-8 text-primary" aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold">选择一次 Run 查看详情</h2>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">这里会展示真实步骤、Skill、模型、工具、用量和错误，不展示隐藏思维或完整 Prompt。</p>
        </div>
      </section>
    );
  }

  const { run } = detail;
  const skill = getVisibleSkill(skills, run.primary_skill);
  const events = stableRunEvents(detail.events);
  const citations = events.map(safeCitation).filter((item): item is NonNullable<typeof item> => item !== null);
  const artifacts = events.map(safeArtifact).filter((item): item is NonNullable<typeof item> => item !== null);
  const capabilities = capabilitySpans(detail.spans);
  const resolvedSkills = Array.isArray(run.resolved_skills) ? run.resolved_skills : [];

  return (
    <article className="min-h-0 flex-1 overflow-y-auto bg-background" aria-labelledby="run-detail-title">
      <div className="mx-auto w-full max-w-5xl px-4 pb-16 pt-5 sm:px-6 lg:px-8">
        <Link to={basePath} className="mb-4 inline-flex min-h-11 items-center gap-2 rounded-xl px-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />返回运行列表
        </Link>

        <header className="border-b border-border pb-6">
          <div className="flex flex-wrap items-center gap-2">
            <RunStatusBadge status={run.status} />
            <span className="text-[11px] text-muted-foreground">{formatRunTime(run.started_at)}</span>
          </div>
          <h2 id="run-detail-title" className="mt-4 break-all font-mono text-lg font-semibold tracking-[-0.02em] sm:text-xl">{run.id}</h2>
          {showConversationLink && <div className="mt-4 flex flex-wrap gap-2">
            <Link to={`/chat/${encodeURIComponent(run.conversation_id)}`} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-primary px-4 text-xs font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25">
              返回关联对话<ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          </div>}
        </header>

        {(run.status === "failed" || run.status === "timed_out" || run.status === "cancelled") && (
          <section className="mt-6 rounded-2xl border border-destructive/25 bg-destructive/5 p-5" aria-labelledby="run-error-title">
            <h2 id="run-error-title" className="flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden="true" />
              {run.status === "timed_out" ? "运行超时" : run.status === "cancelled" ? "运行已取消" : "运行失败"}
            </h2>
            <p className="mt-2 font-mono text-xs text-destructive">{run.error_code || (run.status === "cancelled" ? "user_cancelled" : "unknown_error")}</p>
            {run.error_detail && <p className="mt-2 break-words text-xs leading-5 text-muted-foreground">{run.error_detail.slice(0, 500)}</p>}
          </section>
        )}

        <section className="mt-8" aria-labelledby="run-overview-title">
          <h2 id="run-overview-title" className="text-sm font-semibold">运行概览</h2>
          <dl className="mt-3 grid gap-3 rounded-2xl border border-border bg-card p-5 sm:grid-cols-2 xl:grid-cols-4">
            {showOwner && <Definition term="用户 ID"><span className="font-mono">{run.user_id || "—"}</span></Definition>}
            <Definition term="实际 Skill">{skill?.title ?? run.primary_skill ?? "直接回答"}</Definition>
            <Definition term="选择来源">{skillSourceLabel(run.selection_source as SkillSelectionSource | null)}</Definition>
            <Definition term="Requested">{run.requested_skill || "自动"}</Definition>
            <Definition term="Resolved">{resolvedSkills.length > 0 ? resolvedSkills.join(", ") : "无 Skill"}</Definition>
            <Definition term="Workflow">{run.actual_route || "direct"}</Definition>
            <Definition term="Model ID / Profile">{run.model_id}</Definition>
            <Definition term="实际模型">{run.model_name || "—"}</Definition>
            <Definition term="总耗时">{formatDuration(run.total_duration_ms)}</Definition>
          </dl>
        </section>

        <section className="mt-8" aria-labelledby="run-metrics-title">
          <h2 id="run-metrics-title" className="text-sm font-semibold">用量与调用</h2>
          <div className="mt-3 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {[
              ["总 Token", run.total_tokens],
              ["输入 / 输出", `${numberFormatter.format(run.input_tokens)} / ${numberFormatter.format(run.output_tokens)}`],
              ["模型调用", run.model_call_count],
              ["工具 / 检索", `${numberFormatter.format(run.tool_call_count)} / ${numberFormatter.format(run.retrieval_count)}`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-border bg-card p-4">
                <p className="text-[10px] font-medium text-muted-foreground">{label}</p>
                <p className="mt-2 text-base font-semibold">{typeof value === "number" ? numberFormatter.format(value) : value}</p>
              </div>
            ))}
          </div>
        </section>

		{detail.context_usage && (
		  <section className="mt-8" aria-labelledby="run-context-title">
			<h2 id="run-context-title" className="text-sm font-semibold">本次使用的个人上下文</h2>
			<p className="mt-2 text-xs leading-5 text-muted-foreground">只展示实际冻结到本次 Run 的条目和版本；之后修改不会改变这次运行依据。</p>
			{detail.context_usage.items.length === 0 ? <p className="mt-3 rounded-2xl border border-border bg-card p-5 text-xs text-muted-foreground">这次运行没有读取个人上下文。</p> : <div className="mt-3 grid gap-2 sm:grid-cols-2">{detail.context_usage.items.map((item, index) => item.item_id ? <Link key={`${item.item_id}:${item.revision_id ?? index}`} to={`/space/context/${encodeURIComponent(item.item_id)}`} className="rounded-xl border border-border bg-card p-4 hover:border-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><p className="text-xs font-medium">{item.domain} · {item.type}</p><p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">版本 {item.revision_id ?? "已删除"}</p></Link> : <div key={index} className="rounded-xl border border-border bg-muted/40 p-4 text-xs text-muted-foreground">该上下文已被永久删除</div>)}</div>}
		  </section>
		)}

        <section className="mt-8" aria-labelledby="run-timeline-title">
          <h2 id="run-timeline-title" className="text-sm font-semibold">Activity 时间线</h2>
          {events.length === 0 ? (
            <p className="mt-3 rounded-2xl border border-border bg-card p-5 text-xs text-muted-foreground">这次 Run 没有可展示的 Activity。</p>
          ) : (
            <ol className="mt-4">
              {events.map((event, index) => (
                <li key={`${event.sequence}:${event.type}`} className="relative grid grid-cols-[1.25rem_1fr] gap-3 pb-5">
                  {index < events.length - 1 && <span className="absolute left-[0.34rem] top-4 h-full w-px bg-border" aria-hidden="true" />}
                  <span className={`relative z-10 mt-1 h-3 w-3 rounded-full ${timelineTone(event)}`} aria-hidden="true" />
                  <div className="min-w-0 rounded-xl border border-border bg-card px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="text-xs font-medium text-foreground">{eventLabel(event)}</p>
                      <time className="shrink-0 text-[10px] text-muted-foreground" dateTime={event.occurred_at}>{formatRunTime(event.occurred_at)}</time>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground">
                      <span>#{event.sequence}</span>
                      <span>{event.type}</span>
                      {event.stage && <span>{event.stage}</span>}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        {capabilities.length > 0 && (
          <section className="mt-8" aria-labelledby="run-capabilities-title">
            <h2 id="run-capabilities-title" className="flex items-center gap-2 text-sm font-semibold"><Wrench className="h-4 w-4 text-primary" aria-hidden="true" />Capability 与 Tool</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {capabilities.map((span) => (
                <div key={span.span_id} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate font-mono text-xs font-medium">{span.name}</p>
                    <span className="text-[10px] text-muted-foreground">{span.status}</span>
                  </div>
                  <p className="mt-2 text-[10px] text-muted-foreground">{span.type} · {formatDuration(span.duration_ms)}</p>
                  {span.error_code && <p className="mt-2 break-words font-mono text-[10px] text-destructive">{span.error_code}</p>}
                </div>
              ))}
            </div>
          </section>
        )}

        {(artifacts.length > 0 || citations.length > 0) && (
          <section className="mt-8" aria-labelledby="run-results-title">
            <h2 id="run-results-title" className="text-sm font-semibold">产物与引用</h2>
            {artifacts.length > 0 && (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {artifacts.map((artifact) => (
                  <div key={artifact.id} className="flex min-h-16 items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
                    <FileText className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium">{artifact.type}</p>
                      <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">{artifact.id}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {citations.length > 0 && (
              <div className="mt-3 space-y-2">
                {citations.map((citation) => (
                  <a key={citation.id} href={citation.url} target="_blank" rel="noopener noreferrer" className="group flex min-h-16 items-start gap-3 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:border-primary/30 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <Bot className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block break-words text-xs font-medium">{citation.title}</span>
                      {citation.snippet && <span className="mt-1 block line-clamp-2 text-[11px] leading-5 text-muted-foreground">{citation.snippet}</span>}
                    </span>
                    <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 motion-reduce:transform-none" aria-hidden="true" />
                  </a>
                ))}
              </div>
            )}
          </section>
        )}

        <details className="mt-8 rounded-2xl border border-border bg-card">
          <summary className="flex min-h-11 cursor-pointer items-center gap-2 px-4 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />技术与 provenance 摘要
          </summary>
          <dl className="grid gap-4 border-t border-border p-4 sm:grid-cols-2">
            <Definition term="Protocol">v{run.protocol_version}</Definition>
            <Definition term="Service">{run.service_version || "—"}</Definition>
            <Definition term="Agent">{run.agent_version || "—"}</Definition>
            <Definition term="Graph">{run.graph_version || "—"}</Definition>
            <Definition term="Prompt Bundle Hash">{run.prompt_bundle_hash || "—"}</Definition>
            <Definition term="Execution ID"><span className="font-mono">{run.execution_id}</span></Definition>
            <Definition term="Trace ID"><span className="font-mono">{run.trace_id}</span></Definition>
            <Definition term="Cached Token">{numberFormatter.format(run.cached_tokens)}</Definition>
          </dl>
        </details>
      </div>
    </article>
  );
}
