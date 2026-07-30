import { ConversationStreamEvent } from './chat-api';

export interface RuntimeActivity {
  id: string;
  type: 'tool' | 'progress' | 'artifact' | 'error';
  message: string;
  thinking?: boolean;
  finished?: boolean;
  sequence?: number;
}

export interface StreamState {
  accumulatedContent: string;
  activities: RuntimeActivity[];
  lastSequence: number;
  isStreaming: boolean;
}

export function conversationStreamReducer(state: StreamState, event: ConversationStreamEvent): StreamState {
  const newState = { ...state };

  if (event.type === "meta") {
    newState.isStreaming = true;
    return newState;
  }

  if (event.type === "done" || event.type === "error") {
    newState.isStreaming = false;
    return newState;
  }

  if (event.type === "activity" || event.type === "tool.completed") {
    const activity: RuntimeActivity = {
      id: `activity-${Date.now()}`,
      type: event.type === "tool.completed" ? 'tool' : 'progress',
      message: event.data || '',
      thinking: event.isThinking,
      finished: event.thinkingFinished,
    };
    newState.activities.push(activity);
    return newState;
  }

  if (event.type === "answer_delta" || event.type === "delta") {
    const data = event.type === "answer_delta" ? event.data : (event as any).data;
    const isThinking = event.isThinking === true;
    if (data && !isThinking) {
      newState.accumulatedContent += data;
    }
    return newState;
  }

  return newState;
}