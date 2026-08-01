import type { ProposalItemType, ProposalStatus, WikiProposal } from "@/lib/proposal-api";

export const proposalTypeLabels: Record<ProposalItemType, string> = {
  confirmed_fact: "确认事实",
  current_state: "当前状态",
  personal_rule: "个人规则",
  ai_analysis: "AI 分析",
};

export const proposalStatusLabels: Record<ProposalStatus, string> = {
  pending: "待确认",
  deferred: "已暂缓",
  accepted: "已接受",
  rejected: "已拒绝",
  superseded: "已被新建议替代",
};

export interface ProposalSourceDetail {
  source_excerpt?: string;
  confidence?: number;
  low_confidence?: boolean;
  proposed_action?: "create" | "update";
  conflict_item_ids?: string[];
  explanation?: string;
  extraction_version?: string;
  prompt_version?: string;
  model_version?: string;
  run_id?: string;
  origin_run_id?: string;
}

export function parseProposalSourceDetail(proposal: WikiProposal): ProposalSourceDetail {
  if (!proposal.source_detail) return {};
  try {
    const value = JSON.parse(proposal.source_detail) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const detail = value as ProposalSourceDetail;
    return {
      source_excerpt: typeof detail.source_excerpt === "string" ? detail.source_excerpt : undefined,
      confidence: typeof detail.confidence === "number" && detail.confidence >= 0 && detail.confidence <= 1 ? detail.confidence : undefined,
      low_confidence: detail.low_confidence === true,
      proposed_action: detail.proposed_action === "update" ? "update" : detail.proposed_action === "create" ? "create" : undefined,
      conflict_item_ids: Array.isArray(detail.conflict_item_ids) ? detail.conflict_item_ids.filter((item): item is string => typeof item === "string").slice(0, 20) : [],
      explanation: typeof detail.explanation === "string" ? detail.explanation : undefined,
      extraction_version: typeof detail.extraction_version === "string" ? detail.extraction_version : undefined,
      prompt_version: typeof detail.prompt_version === "string" ? detail.prompt_version : undefined,
      model_version: typeof detail.model_version === "string" ? detail.model_version : undefined,
      run_id: typeof detail.run_id === "string" ? detail.run_id : undefined,
      origin_run_id: typeof detail.origin_run_id === "string" ? detail.origin_run_id : undefined,
    };
  } catch {
    return {};
  }
}
