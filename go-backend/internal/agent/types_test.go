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
