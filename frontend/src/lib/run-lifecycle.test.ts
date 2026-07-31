import { describe, expect, it } from "vitest";

import {
  canCancelRun,
  idleRunLifecycle,
  isRunBusy,
  runLifecycleReducer,
} from "./run-lifecycle";

describe("runLifecycleReducer", () => {
  it("does not allow cancellation before Create returns a run id", () => {
    const creating = runLifecycleReducer(idleRunLifecycle(), {
      type: "create_started",
    });

    expect(isRunBusy(creating)).toBe(true);
    expect(canCancelRun(creating)).toBe(false);
  });

  it("keeps the run active when cancellation fails so the user can retry", () => {
    const active = runLifecycleReducer(idleRunLifecycle(), {
      type: "run_available",
      runID: "run-1",
      assistantMessageID: "message-1",
      protocolVersion: 1,
      status: "running",
    });
    const cancelling = runLifecycleReducer(active, {
      type: "cancel_requested",
      runID: "run-1",
    });
    const retryable = runLifecycleReducer(cancelling, {
      type: "cancel_failed",
      runID: "run-1",
    });

    expect(cancelling.phase).toBe("cancelling");
    expect(retryable.phase).toBe("active");
    expect(canCancelRun(retryable)).toBe(true);
  });

  it("tracks confirmed sequence and only done clears the active run", () => {
    const active = runLifecycleReducer(idleRunLifecycle(), {
      type: "run_available",
      runID: "run-1",
      assistantMessageID: "message-1",
      protocolVersion: 1,
      status: "running",
    });
    const confirmed = runLifecycleReducer(active, {
      type: "event_confirmed",
      runID: "run-1",
      sequence: 8,
    });
    const detached = runLifecycleReducer(confirmed, {
      type: "event_confirmed",
      runID: "other-run",
      sequence: 99,
    });
    const terminal = runLifecycleReducer(detached, {
      type: "done",
      runID: "run-1",
    });

    expect(confirmed.lastSequence).toBe(8);
    expect(detached).toBe(confirmed);
    expect(terminal).toEqual(idleRunLifecycle());
  });
});
