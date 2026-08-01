import { describe, expect, it } from "vitest";

import type { StoredMessage } from "@/lib/chat-api";
import {
  mergeStoredMessage,
  toViewMessages,
  type ChatViewMessage,
} from "./chat-message-state";

const terminalMessage: StoredMessage = {
  id: "assistant-1",
  conversation_id: "conversation-1",
  role: "assistant",
  content: "这个请求可能更适合使用命理分析。确认后我会在下一条消息中执行。",
  status: "completed",
  sequence_id: 2,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:01Z",
};

describe("mergeStoredMessage", () => {
  it("preserves the confirmation action when terminal history refreshes", () => {
    const current: ChatViewMessage = {
      ...terminalMessage,
      status: "streaming",
      thinking: true,
      confirmation: {
        skillID: "fortune",
        confidence: 0.94,
        prompt: "请帮我看看八字",
      },
      runID: "run-1",
    };

    const stored = toViewMessages([terminalMessage])[0];
    expect(mergeStoredMessage(current, stored)).toMatchObject({
      status: "completed",
      thinking: false,
      confirmation: current.confirmation,
      runID: "run-1",
    });
  });

  it("does not replace an actively streaming projection", () => {
    const current: ChatViewMessage = {
      ...terminalMessage,
      status: "streaming",
      content: "partial",
    };
    const incoming = {
      ...toViewMessages([terminalMessage])[0],
      status: "streaming" as const,
    };

    expect(mergeStoredMessage(current, incoming)).toBe(current);
  });

  it("restores a persisted confirmation with the preceding user prompt", () => {
    const userMessage: StoredMessage = {
      ...terminalMessage,
      id: "user-1",
      role: "user",
      content: "请帮我看看八字",
      sequence_id: 1,
    };
    const assistantMessage: StoredMessage = {
      ...terminalMessage,
      metadata: {
        skill_confirmation: {
          suggested_skill: "fortune",
          confidence: 0.94,
          reason_code: "automatic_confirmation_required",
        },
      },
    };

    expect(toViewMessages([userMessage, assistantMessage])[1].confirmation)
      .toEqual({
        skillID: "fortune",
        confidence: 0.94,
        prompt: "请帮我看看八字",
      });
  });
});
