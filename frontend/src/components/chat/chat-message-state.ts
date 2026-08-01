import type {
  RuntimeActivity,
  RuntimeArtifact,
  RuntimeCitation,
  StoredMessage,
} from "@/lib/chat-api";
import type {
  SkillID,
  SkillSelectionSource,
} from "@/features/skills/skills";
import { parseStoredCitations } from "@/features/citations/citations";
import type { ChatRole } from "./ChatMessage";

export interface ChatViewMessage {
  id: string;
  role: ChatRole;
  content: string;
  status?: StoredMessage["status"];
  thinking?: boolean;
  thinkingFinished?: boolean;
  activities?: RuntimeActivity[];
  artifacts?: RuntimeArtifact[];
  citations?: RuntimeCitation[];
  skillID?: SkillID | null;
  skillSource?: SkillSelectionSource | null;
  confirmation?: {
    skillID: SkillID;
    confidence: number;
    prompt: string;
  };
  runID?: string;
  contextUsage?: { runID: string; purpose: string; items: Array<{ itemID: string; type: string; domain: string }> };
}

function parseStoredContextUsage(metadata?: Record<string, unknown>) {
  const value = metadata?.context_usage;
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const usage = value as Record<string, unknown>;
  if (typeof usage.run_id !== "string" || typeof usage.purpose !== "string" || !Array.isArray(usage.items)) return undefined;
  const items = usage.items.flatMap((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    const row = item as Record<string, unknown>;
    return typeof row.item_id === "string" && typeof row.type === "string" && typeof row.domain === "string"
      ? [{ itemID: row.item_id, type: row.type, domain: row.domain }]
      : [];
  }).slice(0, 50);
  return { runID: usage.run_id, purpose: usage.purpose, items };
}

function parseStoredConfirmation(metadata?: Record<string, unknown>) {
  const value = metadata?.skill_confirmation;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const confirmation = value as Record<string, unknown>;
  if (
    typeof confirmation.suggested_skill !== "string" ||
    !/^[a-z][a-z0-9_]{0,63}$/.test(confirmation.suggested_skill) ||
    typeof confirmation.confidence !== "number" ||
    confirmation.confidence < 0 ||
    confirmation.confidence > 1 ||
    confirmation.reason_code !== "automatic_confirmation_required"
  ) {
    return null;
  }
  return {
    skillID: confirmation.suggested_skill,
    confidence: confirmation.confidence,
  };
}

function toViewMessage(
  message: StoredMessage,
  precedingUserPrompt: string,
): ChatViewMessage {
  const storedConfirmation = parseStoredConfirmation(message.metadata);
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    status: message.status,
    thinking: message.status === "streaming",
    thinkingFinished: message.status !== "streaming",
    citations: parseStoredCitations(message.metadata),
    contextUsage: message.role === "assistant" ? parseStoredContextUsage(message.metadata) : undefined,
    confirmation:
      message.role === "assistant" &&
      storedConfirmation &&
      precedingUserPrompt
        ? { ...storedConfirmation, prompt: precedingUserPrompt }
        : undefined,
  };
}

export function toViewMessages(messages: StoredMessage[]): ChatViewMessage[] {
  let precedingUserPrompt = "";
  return messages.map((message) => {
    if (message.role === "user") precedingUserPrompt = message.content;
    return toViewMessage(message, precedingUserPrompt);
  });
}

export function mergeStoredMessage(
  current: ChatViewMessage,
  stored: ChatViewMessage,
): ChatViewMessage {
  if (current.status === "streaming" && stored.status === "streaming") {
    return current;
  }

  return {
    ...stored,
    activities: current.activities,
    artifacts: current.artifacts,
    citations:
      stored.citations && stored.citations.length > 0
        ? stored.citations
        : current.citations,
    skillID: current.skillID,
    skillSource: current.skillSource,
    confirmation: stored.confirmation ?? current.confirmation,
    runID: current.runID,
    contextUsage: stored.contextUsage ?? current.contextUsage,
  };
}
