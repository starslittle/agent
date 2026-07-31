import type { AgentRunStatus } from "./chat-api";

export type RunLifecycleState =
  | { phase: "idle"; lastSequence: 0 }
  | { phase: "creating"; lastSequence: 0 }
  | {
      phase: "active" | "cancelling";
      runID: string;
      assistantMessageID: string;
      protocolVersion: number;
      lastSequence: number;
    };

export type RunLifecycleAction =
  | { type: "create_started" }
  | {
      type: "run_available";
      runID: string;
      assistantMessageID: string;
      protocolVersion: number;
      status: AgentRunStatus;
    }
  | { type: "event_confirmed"; runID: string; sequence?: number }
  | { type: "cancel_requested"; runID: string }
  | { type: "cancel_failed"; runID: string }
  | { type: "done"; runID: string }
  | { type: "create_failed" };

export const idleRunLifecycle = (): RunLifecycleState => ({
  phase: "idle",
  lastSequence: 0,
});

export function runLifecycleReducer(
  state: RunLifecycleState,
  action: RunLifecycleAction,
): RunLifecycleState {
  switch (action.type) {
    case "create_started":
      return state.phase === "idle"
        ? { phase: "creating", lastSequence: 0 }
        : state;
    case "run_available":
      return {
        phase: action.status === "cancel_requested" ? "cancelling" : "active",
        runID: action.runID,
        assistantMessageID: action.assistantMessageID,
        protocolVersion: action.protocolVersion,
        lastSequence: 0,
      };
    case "event_confirmed":
      if (
        (state.phase !== "active" && state.phase !== "cancelling") ||
        state.runID !== action.runID ||
        action.sequence === undefined ||
        action.sequence <= state.lastSequence
      ) {
        return state;
      }
      return { ...state, lastSequence: action.sequence };
    case "cancel_requested":
      return state.phase === "active" && state.runID === action.runID
        ? { ...state, phase: "cancelling" }
        : state;
    case "cancel_failed":
      return state.phase === "cancelling" && state.runID === action.runID
        ? { ...state, phase: "active" }
        : state;
    case "done":
      return (state.phase === "active" || state.phase === "cancelling") &&
        state.runID === action.runID
        ? idleRunLifecycle()
        : state;
    case "create_failed":
      return state.phase === "creating" ? idleRunLifecycle() : state;
  }
}

export function canCancelRun(state: RunLifecycleState): boolean {
  return state.phase === "active";
}

export function isRunBusy(state: RunLifecycleState): boolean {
  return state.phase !== "idle";
}
