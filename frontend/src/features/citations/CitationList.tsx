import { ExternalLink } from "lucide-react";
import type { RuntimeCitation } from "@/lib/chat-api";
import { citationAnchorID, sortedCitations } from "./citations";

interface CitationListProps {
  citations: RuntimeCitation[];
  scope: string;
}

const sourceTypeLabels: Record<RuntimeCitation["source_type"], string> = {
  web: "网页",
  knowledge: "知识库",
  tool: "工具",
};

export function CitationList({ citations, scope }: CitationListProps) {
  const items = sortedCitations(citations);
  if (items.length === 0) return null;
  const headingID = `${citationAnchorID(scope, "heading")}-label`;
  const formattedCount = new Intl.NumberFormat("zh-CN").format(items.length);

  return (
    <section className="mt-5 border-t border-border/70 pt-4" aria-labelledby={headingID}>
      <div className="mb-2.5 flex items-baseline justify-between gap-3">
        <h3 id={headingID} className="text-xs font-semibold text-foreground">
          来源
        </h3>
        <span className="text-xs tabular-nums text-muted-foreground">
          {formattedCount} 项
        </span>
      </div>
      <ol className="space-y-2">
        {items.map((citation, index) => {
          const displayIndex = index + 1;
          const hostname = new URL(citation.url).hostname.replace(/^www\./, "");
          return (
            <li
              key={citation.citation_id}
              id={citationAnchorID(scope, citation.citation_id)}
              className="scroll-mt-6"
            >
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`打开来源 ${displayIndex}：${citation.title}（新窗口）`}
                className="group/source flex min-h-11 min-w-0 touch-manipulation items-start gap-3 rounded-xl border border-border/70 bg-background/55 px-3 py-2.5 text-left transition-[color,background-color,border-color] hover:border-primary/30 hover:bg-primary/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
              >
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold tabular-nums text-primary">
                  {displayIndex}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-start justify-between gap-2">
                    <span className="min-w-0 break-words text-xs font-medium leading-5 text-foreground">
                      {citation.title}
                    </span>
                    <ExternalLink
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover/source:text-primary"
                      aria-hidden="true"
                    />
                  </span>
                  {citation.snippet && (
                    <span className="mt-1 block break-words text-xs leading-5 text-muted-foreground">
                      {citation.snippet}
                    </span>
                  )}
                  <span className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span>{sourceTypeLabels[citation.source_type]}</span>
                    <span aria-hidden="true">·</span>
                    <span className="min-w-0 break-all" translate="no">
                      {hostname}
                    </span>
                  </span>
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
