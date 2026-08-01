import { describe, expect, it } from "vitest";

import type { WikiProposal } from "@/lib/proposal-api";

import { parseProposalSourceDetail } from "./proposal-presentation";

const proposal = (sourceDetail: string | null): WikiProposal => ({
  id: "proposal-1",
  operation: "create",
  item_type: "current_state",
  domain: "career",
  proposed_content: "正在准备秋招",
  source_type: "document_extracted",
  source_detail: sourceDetail,
  status: "pending",
  version: 1,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
});

describe("proposal source presentation", () => {
  it("keeps valid provenance and drops unsafe shapes", () => {
    expect(parseProposalSourceDetail(proposal(JSON.stringify({
      source_excerpt: "原文",
      confidence: 0.72,
      conflict_item_ids: ["item-1", 7],
      run_id: "run-1",
    })))).toEqual(expect.objectContaining({
      source_excerpt: "原文",
      confidence: 0.72,
      conflict_item_ids: ["item-1"],
      run_id: "run-1",
    }));
  });

  it("treats malformed legacy detail as optional metadata", () => {
    expect(parseProposalSourceDetail(proposal("not-json"))).toEqual({});
  });
});
