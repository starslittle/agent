package agent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestStateMachine(t *testing.T) {
	if !CanTransition(StatusQueued, StatusCancelRequested) {
		t.Fatal("queued must be cancellable before running")
	}
	if !CanTransition(StatusCancelRequested, StatusCancelled) {
		t.Fatal("cancel_requested must transition to cancelled")
	}
	if CanTransition(StatusCompleted, StatusRunning) {
		t.Fatal("terminal state must not regress")
	}
}

func TestProtocolFixture(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("testdata", "agent_protocol_v1_events.json"))
	if err != nil {
		t.Fatal(err)
	}
	var events []Event
	if err := json.Unmarshal(content, &events); err != nil {
		t.Fatal(err)
	}
	for index, event := range events {
		if err := event.Validate("exec_fixture_001"); err != nil {
			t.Fatalf("event %d: %v", index, err)
		}
		expected := int64(index + 1)
		if event.Sequence != expected {
			t.Fatalf("sequence = %d, want %d", event.Sequence, expected)
		}
	}
	if got := events[1].SSEID(); got != "exec_fixture_001:2" {
		t.Fatalf("SSEID() = %q", got)
	}
}

func TestBrowserEventTypes(t *testing.T) {
	if BrowserEventMeta != "meta" {
		t.Fatal("BrowserEventMeta const mismatch")
	}
	if BrowserEventAnswerDelta != "answer_delta" {
		t.Fatal("answer_delta const mismatch")
	}
	if BrowserEventDone != "done" {
		t.Fatal("done const mismatch")
	}
	if BrowserEventError != "error" {
		t.Fatal("error const mismatch")
	}
}

func TestCreateRunResponseContract(t *testing.T) {
	resp := CreateRunResponse{
		ConversationID:      "conv_123",
		UserMessageID:       "msg_456",
		AssistantMessageID:  "msg_789",
		RunID:               "run_abc",
		ExecutionID:         "exec_def",
		ProtocolVersion:     1,
		Status:              "queued",
		EventsURL:          "/api/v1/agent-runs/run_abc/events",
		ClientMessageID:     "client_msg_999",
	}
	if resp.Status != "queued" {
		t.Fatal("status mismatch")
	}
	if resp.ClientMessageID == "" {
		t.Fatal("client_message_id required")
	}
}

func TestTerminalStatusMapping(t *testing.T) {
	if TerminalStatusToAssistantStatus(StatusCancelled) != "stopped" {
		t.Fatal("cancelled should map to stopped")
	}
	if TerminalStatusToAssistantStatus(StatusCompleted) != "completed" {
		t.Fatal("completed should map to completed")
	}
	if TerminalStatusToAssistantStatus(StatusFailed) != "failed" {
		t.Fatal("failed should map to failed")
	}
}
