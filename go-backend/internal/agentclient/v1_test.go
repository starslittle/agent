package agentclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

func TestV1ClientStreamsTypedEvents(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/internal/v1/agent-runs:stream" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if r.Header.Get("X-Qidian-Signature-Version") != "v1" {
			t.Fatal("missing v1 signature")
		}
		var request agent.RunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		w.Header().Set("Content-Type", "text/event-stream")
		for sequence, eventType := range []string{
			"run.started",
			"answer.delta",
			"run.completed",
		} {
			event := agent.Event{
				ProtocolVersion: agent.ProtocolVersion,
				ExecutionID:     request.ExecutionID,
				RunID:           request.RunID,
				Sequence:        int64(sequence + 1),
				Type:            eventType,
				OccurredAt:      time.Now().UTC(),
				Data:            json.RawMessage(`{}`),
			}
			data, _ := json.Marshal(event)
			_, _ = fmt.Fprintf(
				w,
				"event: %s\nid: %s\ndata: %s\n\n",
				event.Type,
				event.SSEID(),
				data,
			)
		}
	}))
	defer upstream.Close()

	client, err := NewV1(
		upstream.URL,
		upstream.Client(),
		"test-secret-that-is-at-least-32-characters",
	)
	if err != nil {
		t.Fatal(err)
	}
	stream, err := client.Start(context.Background(), agent.RunRequest{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     "exec-1",
		RunID:           "run-1",
		RequestID:       "req-1",
		IdempotencyKey:  "exec-1",
		ConversationID:  "conv-1",
		AgentName:       "default_llm_agent",
		Query:           "hello",
		DeadlineMS:      1000,
		UserID:          "user-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	for sequence := int64(1); sequence <= 3; sequence++ {
		event, err := stream.Next()
		if err != nil {
			t.Fatal(err)
		}
		if event.Sequence != sequence {
			t.Fatalf("sequence = %d, want %d", event.Sequence, sequence)
		}
	}
	if _, err := stream.Next(); err != io.EOF {
		t.Fatalf("final error = %v, want EOF", err)
	}
}
