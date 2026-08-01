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
}

function parseStoredConfirmation(metadata?: Record<string, unknown>) {
  const value = metadata?.skill_confirmation;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const confirmation = value as Record<string, unknown>;
  if (
    (confirmation.suggested_skill !== "research" &&
      confirmation.suggested_skill !== "fortune") ||
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
  };
}
