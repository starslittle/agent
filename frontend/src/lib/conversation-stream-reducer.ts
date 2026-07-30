import {
  type ConversationStreamEvent,
  type RuntimeActivity,
  type RuntimeArtifact,
} from "./chat-api";

export interface ConversationStreamState {
  answer: string;
  activities: RuntimeActivity[];
  artifacts: RuntimeArtifact[];
  lastSequence: number;
  legacyActivitySequence: number;
  isStreaming: boolean;
  terminalStatus?: string;
}

export function createConversationStreamState(): ConversationStreamState {
  return {
    answer: "",
    activities: [],
    artifacts: [],
    lastSequence: 0,
    legacyActivitySequence: 0,
    isStreaming: false,
  };
}

export function conversationStreamReducer(
  state: ConversationStreamState,
  event: ConversationStreamEvent,
): ConversationStreamState {
  const sequence = "sequence" in event ? event.sequence : undefined;
  const lastSequence =
    typeof sequence === "number"
      ? Math.max(state.lastSequence, sequence)
      : state.lastSequence;

  switch (event.type) {
    case "meta":
      return {
        ...state,
        lastSequence,
        isStreaming: true,
      };
    case "answer_delta":
      return {
        ...state,
        answer: state.answer + event.data,
        lastSequence,
      };
    case "activity":
      return {
        ...state,
        activities: upsertActivity(state.activities, event.activity),
        lastSequence,
      };
    case "artifact":
      return {
        ...state,
        artifacts: upsertArtifact(state.artifacts, event.artifact),
        lastSequence,
      };
    case "delta":
      return reduceLegacyDelta(state, event);
    case "done":
      return {
        ...state,
        lastSequence,
        isStreaming: false,
        terminalStatus: event.status,
      };
    case "error":
      return {
        ...state,
        lastSequence,
        isStreaming: false,
        terminalStatus: "failed",
      };
  }
}

function reduceLegacyDelta(
  state: ConversationStreamState,
  event: Extract<ConversationStreamEvent, { type: "delta" }>,
): ConversationStreamState {
  if (event.isThinking !== true) {
    return {
      ...state,
      answer: state.answer + (event.data ?? ""),
      isStreaming: true,
    };
  }

  const legacyActivitySequence = state.legacyActivitySequence + 1;
  const status = event.thinkingFinished ? "completed" : "running";
  const activity: RuntimeActivity = {
    id: `legacy:${legacyActivitySequence}`,
    kind: "progress",
    status,
    label: event.thinkingFinished ? "处理完成" : "正在处理请求",
  };
  return {
    ...state,
    activities: [...state.activities, activity],
    legacyActivitySequence,
    isStreaming: true,
  };
}

function upsertActivity(
  activities: RuntimeActivity[],
  incoming: RuntimeActivity,
): RuntimeActivity[] {
  const existingIndex = activities.findIndex(
    (activity) => activity.id === incoming.id,
  );
  const next =
    existingIndex === -1
      ? [...activities, incoming]
      : activities.map((activity, index) =>
          index === existingIndex ? incoming : activity,
        );
  return next
    .map((activity, index) => ({ activity, index }))
    .sort((left, right) => {
      const leftSequence = left.activity.sequence;
      const rightSequence = right.activity.sequence;
      if (leftSequence === undefined && rightSequence === undefined) {
        return left.index - right.index;
      }
      if (leftSequence === undefined) return 1;
      if (rightSequence === undefined) return -1;
      return leftSequence - rightSequence || left.index - right.index;
    })
    .map(({ activity }) => activity);
}

function upsertArtifact(
  artifacts: RuntimeArtifact[],
  incoming: RuntimeArtifact,
): RuntimeArtifact[] {
  const existingIndex = artifacts.findIndex(
    (artifact) => artifact.artifact_id === incoming.artifact_id,
  );
  if (existingIndex === -1) {
    return [...artifacts, incoming];
  }
  return artifacts.map((artifact, index) =>
    index === existingIndex ? incoming : artifact,
  );
}
