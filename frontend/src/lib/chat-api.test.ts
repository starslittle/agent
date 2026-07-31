import { afterEach, describe, expect, it, vi } from "vitest";

import {
  attachAgentRun,
  createAgentRun,
  type ConversationStreamEvent,
} from "./chat-api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Agent Run API", () => {
  it("creates a run before attaching and sends the idempotency key", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            run_id: "run-1",
            execution_id: "execution-1",
            conversation_id: "conversation-1",
            user_message_id: "user-message-1",
            assistant_message_id: "assistant-message-1",
            status: "queued",
            protocol_version: 1,
            events_url: "/api/v1/agent-runs/run-1/events",
          }),
          {
            status: 201,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await createAgentRun(
      "conversation-1",
      {
        content: "继续运行",
        client_message_id: "client-1",
        idempotency_key: "client-1",
      },
      "csrf-1",
    );

    expect(result.run_id).toBe("run-1");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/conversations/conversation-1/runs");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-1");
    expect(init?.body).toContain('"idempotency_key":"client-1"');
  });

  it("reattaches after the last confirmed sequence and stops at done", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          [
            "event: message",
            'data: {"type":"answer_delta","sequence":8,"data":"恢复"}',
            "",
            "event: message",
            'data: {"type":"done","sequence":9,"status":"completed"}',
            "",
          ].join("\n"),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const events: ConversationStreamEvent[] = [];

    await attachAgentRun("run-1", 7, (event) => events.push(event));

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/agent-runs/run-1/events?starting_after=7",
    );
    expect(events.map((event) => event.type)).toEqual(["answer_delta", "done"]);
  });

  it("treats a sequence gap as a reconnectable attach failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            [
              "event: message",
              'data: {"type":"error","code":"agent_event_sequence_gap","expected_sequence":3,"received_sequence":4}',
              "",
            ].join("\n"),
            { status: 200 },
          ),
      ),
    );

    await expect(attachAgentRun("run-1", 2, () => undefined)).rejects.toThrow(
      "运行事件暂时不连续，正在重新连接",
    );
  });
});
