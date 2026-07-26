package agentclient

import (
	"context"
	"encoding/json"
	"errors"
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

func TestV1ClientResumeStartsAfterConfirmedSequence(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		if got := r.URL.Query().Get("starting_after"); got != "2" {
			t.Fatalf("starting_after = %q, want 2", got)
		}
		var request agent.RunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		writeAgentEvent(t, w, request, 3, "answer.delta", `{"text":"ok"}`)
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
	run := testRunRequest()
	stream, err := client.Resume(context.Background(), run, 2)
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	event, err := stream.Next()
	if err != nil {
		t.Fatal(err)
	}
	if event.Sequence != 3 {
		t.Fatalf("sequence = %d, want 3", event.Sequence)
	}
}

func TestV1EventStreamGapDoesNotAdvanceConfirmedCursor(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		var request agent.RunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		writeAgentEvent(t, w, request, 1, "run.started", `{}`)
		writeAgentEvent(t, w, request, 3, "answer.delta", `{"text":"late"}`)
		writeAgentEvent(t, w, request, 2, "answer.delta", `{"text":"replayed"}`)
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
	stream, err := client.Start(context.Background(), testRunRequest())
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	if event, err := stream.Next(); err != nil || event.Sequence != 1 {
		t.Fatalf("first event = %#v, error = %v", event, err)
	}
	if event, err := stream.Next(); !errors.Is(err, agent.ErrSequenceGap) ||
		event.Sequence != 3 {
		t.Fatalf("gap event = %#v, error = %v", event, err)
	}
	if event, err := stream.Next(); err != nil || event.Sequence != 2 {
		t.Fatalf("replayed event = %#v, error = %v", event, err)
	}
}

func TestV1EventStreamDetectsGapAtFirstEvent(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		var request agent.RunRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Fatal(err)
		}
		writeAgentEvent(t, w, request, 2, "answer.delta", `{"text":"late"}`)
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
	stream, err := client.Start(context.Background(), testRunRequest())
	if err != nil {
		t.Fatal(err)
	}
	defer stream.Close()
	event, err := stream.Next()
	if !errors.Is(err, agent.ErrSequenceGap) || event.Sequence != 2 {
		t.Fatalf("first event = %#v, error = %v", event, err)
	}
}

func testRunRequest() agent.RunRequest {
	return agent.RunRequest{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     "exec-replay",
		RunID:           "run-replay",
		RequestID:       "req-replay",
		IdempotencyKey:  "exec-replay",
		ConversationID:  "conv-replay",
		AgentName:       "default_llm_agent",
		Query:           "hello",
		DeadlineMS:      1000,
		UserID:          "user-replay",
	}
}

func writeAgentEvent(
	t *testing.T,
	w http.ResponseWriter,
	request agent.RunRequest,
	sequence int64,
	eventType string,
	data string,
) {
	t.Helper()
	event := agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     request.ExecutionID,
		RunID:           request.RunID,
		Sequence:        sequence,
		Type:            eventType,
		OccurredAt:      time.Now().UTC(),
		Data:            json.RawMessage(data),
	}
	encoded, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = fmt.Fprintf(
		w,
		"event: %s\nid: %s\ndata: %s\n\n",
		event.Type,
		event.SSEID(),
		encoded,
	)
}
