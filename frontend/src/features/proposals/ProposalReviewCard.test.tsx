import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { WikiProposal } from "@/lib/proposal-api";

import { ProposalReviewCard } from "./ProposalReviewCard";

function makeProposal(overrides: Partial<WikiProposal> = {}): WikiProposal {
  return {
    id: "proposal-1",
    operation: "update",
    item_type: "current_state",
    domain: "career",
    proposed_content: "正在集中准备秋招",
    source_type: "document_extracted",
    source_detail: JSON.stringify({ confidence: 0.42, low_confidence: true, conflict_item_ids: ["item-1"] }),
    document_id: "doc-1",
    document_revision_id: "revision-1",
    status: "pending",
    version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("ProposalReviewCard", () => {
  it("shows provenance risk and all four explicit decisions while actionable", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ProposalReviewCard proposal={makeProposal()} csrfToken="csrf" onResolved={() => undefined} onReload={() => undefined} />
      </MemoryRouter>,
    );

    expect(html).toContain("正在集中准备秋招");
    expect(html).toContain("置信度 42%");
    expect(html).toContain("已有信息可能与它冲突");
    expect(html).toContain("接受");
    expect(html).toContain("修改后接受");
    expect(html).toContain("暂缓");
    expect(html).toContain("拒绝");
  });

  it("shows the adopted edit after refresh and removes mutation actions", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ProposalReviewCard
          proposal={makeProposal({ status: "accepted", final_content: "最终确认的秋招状态", resolution_action: "accept" })}
          csrfToken="csrf"
          onResolved={() => undefined}
          onReload={() => undefined}
        />
      </MemoryRouter>,
    );

    expect(html).toContain("已写入关联上下文");
    expect(html).toContain("最终确认的秋招状态");
    expect(html).not.toContain(">修改后接受<");
  });
});
