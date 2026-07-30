import { describe, expect, it } from "vitest";

import {
  createConversationStreamState,
  conversationStreamReducer,
} from "./conversation-stream-reducer";
import {
  parseConversationStreamEvent,
  type ConversationStreamEvent,
  type RuntimeActivity,
} from "./chat-api";

function activityEvent(
  id: string,
  sequence: number,
  status: RuntimeActivity["status"] = "completed",
): Extract<ConversationStreamEvent, { type: "activity" }> {
  return {
    type: "activity",
    sequence,
    activity: {
      id,
      sequence,
      kind: "tool",
      status,
      label: "联网检索完成",
      name: "tavily_search",
    },
  };
}

describe("conversationStreamReducer", () => {
  it("keeps activity out of the answer and preserves the input state", () => {
    const state = createConversationStreamState();
    const next = conversationStreamReducer(state, activityEvent("tool:1", 1));

    expect(next.answer).toBe("");
    expect(next.activities).toHaveLength(1);
    expect(state.activities).toEqual([]);
    expect(next.activities).not.toBe(state.activities);
  });

  it("uses answer_delta as the V1 answer source", () => {
    const state = conversationStreamReducer(
      createConversationStreamState(),
      { type: "answer_delta", sequence: 1, data: "第一段" },
    );
    const next = conversationStreamReducer(state, {
      type: "answer_delta",
      sequence: 2,
      data: "第二段",
    });

    expect(next.answer).toBe("第一段第二段");
    expect(next.activities).toEqual([]);
    expect(next.lastSequence).toBe(2);
  });

  it("preserves five real tool calls without adding answer text", () => {
    const next = Array.from({ length: 5 }, (_, index) => index + 1).reduce(
      (state, sequence) =>
        conversationStreamReducer(
          state,
          activityEvent(`tool:${sequence}`, sequence),
        ),
      createConversationStreamState(),
    );

    expect(next.activities).toHaveLength(5);
    expect(next.answer).toBe("");
  });

  it("converts legacy thinking delta into a safe activity", () => {
    const next = conversationStreamReducer(createConversationStreamState(), {
      type: "delta",
      data: "Step1: secret internal detail",
      isThinking: true,
      thinkingFinished: false,
    });

    expect(next.answer).toBe("");
    expect(next.activities).toEqual([
      {
        id: "legacy:1",
        kind: "progress",
        status: "running",
        label: "正在处理请求",
      },
    ]);
    expect(JSON.stringify(next)).not.toContain("secret internal detail");
  });

  it("keeps legacy non-thinking delta as answer text", () => {
    const next = conversationStreamReducer(createConversationStreamState(), {
      type: "delta",
      data: "legacy answer",
      isThinking: false,
      thinkingFinished: true,
    });

    expect(next.answer).toBe("legacy answer");
    expect(next.activities).toEqual([]);
  });

  it("keeps artifacts outside the answer and deduplicates by id", () => {
    const event: ConversationStreamEvent = {
      type: "artifact",
      sequence: 3,
      artifact: {
        artifact_id: "report:1",
        artifact_type: "research_report",
        content_hash: "abc",
        mime_type: "application/json",
        size_bytes: 42,
      },
    };
    const state = conversationStreamReducer(
      createConversationStreamState(),
      event,
    );
    const next = conversationStreamReducer(state, event);

    expect(next.answer).toBe("");
    expect(next.artifacts).toHaveLength(1);
  });

  it("deduplicates activities and orders them by sequence", () => {
    const state = conversationStreamReducer(
      createConversationStreamState(),
      activityEvent("tool:2", 2, "started"),
    );
    const reordered = conversationStreamReducer(
      state,
      activityEvent("tool:1", 1),
    );
    const updated = conversationStreamReducer(reordered, {
      ...activityEvent("tool:2", 2, "completed"),
      activity: {
        ...activityEvent("tool:2", 2, "completed").activity,
        label: "联网检索完成",
      },
    });

    expect(updated.activities.map((activity) => activity.id)).toEqual([
      "tool:1",
      "tool:2",
    ]);
    expect(updated.activities[1].status).toBe("completed");
  });

  it("does not append done or error messages to the answer", () => {
    const answered = conversationStreamReducer(
      createConversationStreamState(),
      { type: "answer_delta", sequence: 1, data: "保留正文" },
    );
    const done = conversationStreamReducer(answered, {
      type: "done",
      status: "completed",
    });
    const failed = conversationStreamReducer(answered, {
      type: "error",
      message: "internal failure",
    });

    expect(done.answer).toBe("保留正文");
    expect(done.isStreaming).toBe(false);
    expect(failed.answer).toBe("保留正文");
    expect(JSON.stringify(failed)).not.toContain("internal failure");
  });
});

describe("parseConversationStreamEvent", () => {
  it("ignores malformed and unknown browser events", () => {
    expect(parseConversationStreamEvent("{")).toBeNull();
    expect(
      parseConversationStreamEvent(
        JSON.stringify({ type: "unknown", data: "must not become answer" }),
      ),
    ).toBeNull();
    expect(
      parseConversationStreamEvent(
        JSON.stringify({ type: "answer_delta", data: 42 }),
      ),
    ).toBeNull();
  });

  it("accepts a strongly typed activity event", () => {
    const event = activityEvent("tool:1", 1);
    expect(parseConversationStreamEvent(JSON.stringify(event))).toEqual(event);
  });
});
