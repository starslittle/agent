package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func TestAttachRunEventsReplaysThenFollowsToOneTerminalEvent(t *testing.T) {
	store := &attachRunStore{
		userID: "user-1",
		pages: []conversation.RunEventPage{
			attachPage("running", "streaming", []agent.Event{
				attachEvent(1, "run.started", `{}`),
				attachEvent(2, "answer.delta", `{"text":"重放"}`),
			}),
			attachPage("completed", "completed", []agent.Event{
				attachEvent(3, "run.completed", `{}`),
			}),
		},
	}
	handler := newAttachTestHandler(store)
	request := attachTestRequest("user-1", 1)
	response := httptest.NewRecorder()

	handler.attachRunEvents(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	if !strings.Contains(body, `"type":"answer_delta","sequence":2,"data":"重放"`) {
		t.Fatalf("missing replayed answer: %s", body)
	}
	if strings.Count(body, `"type":"done"`) != 1 ||
		!strings.Contains(body, `"sequence":3,"status":"completed"`) {
		t.Fatalf("terminal event mismatch: %s", body)
	}
}

func TestAttachRunEventsFailsClosedOnSequenceGap(t *testing.T) {
	store := &attachRunStore{
		userID: "user-1",
		pages: []conversation.RunEventPage{
			attachPage("running", "streaming", []agent.Event{
				attachEvent(2, "answer.delta", `{"text":"不可见"}`),
			}),
		},
	}
	response := httptest.NewRecorder()
	newAttachTestHandler(store).attachRunEvents(
		response,
		attachTestRequest("user-1", 0),
	)

	body := response.Body.String()
	if !strings.Contains(body, `"code":"agent_event_sequence_gap"`) ||
		strings.Contains(body, "不可见") {
		t.Fatalf("gap did not fail closed: %s", body)
	}
}

func TestAttachRunEventsEnforcesOwnershipAndDetachDoesNotCancel(t *testing.T) {
	store := &attachRunStore{userID: "owner"}
	handler := newAttachTestHandler(store)

	denied := httptest.NewRecorder()
	handler.attachRunEvents(denied, attachTestRequest("other", 0))
	if denied.Code != http.StatusNotFound {
		t.Fatalf("cross-user status = %d, want 404", denied.Code)
	}

	ctx, cancel := context.WithCancel(context.Background())
	request := attachTestRequest("owner", 0).WithContext(
		context.WithValue(ctx, sessionContextKey{}, auth.Session{
			User: auth.User{ID: "owner"},
		}),
	)
	response := httptest.NewRecorder()
	done := make(chan struct{})
	go func() {
		defer close(done)
		handler.attachRunEvents(response, request)
	}()
	time.Sleep(20 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("attach did not detach after client cancellation")
	}
	store.mu.Lock()
	cancelRequests := store.cancelRequests
	store.mu.Unlock()
	if cancelRequests != 0 {
		t.Fatalf("disconnect requested cancellation %d times", cancelRequests)
	}
}

type attachRunStore struct {
	conversation.Store
	mu             sync.Mutex
	userID         string
	pages          []conversation.RunEventPage
	calls          int
	cancelRequests int
}

func (s *attachRunStore) ListAgentRunEvents(
	_ context.Context,
	userID string,
	_ string,
	startingAfter int64,
	_ int,
) (conversation.RunEventPage, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if userID != s.userID {
		return conversation.RunEventPage{}, conversation.ErrNotFound
	}
	if len(s.pages) == 0 {
		return attachPage("running", "streaming", nil), nil
	}
	index := s.calls
	if index >= len(s.pages) {
		index = len(s.pages) - 1
	}
	s.calls++
	page := s.pages[index]
	filtered := make([]agent.Event, 0, len(page.Events))
	for _, event := range page.Events {
		if event.Sequence > startingAfter {
			filtered = append(filtered, event)
		}
	}
	page.Events = filtered
	return page, nil
}

func (s *attachRunStore) RequestRunCancellation(
	_ context.Context,
	_ string,
	_ string,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cancelRequests++
	return nil
}

func newAttachTestHandler(store conversation.Store) *conversationHTTP {
	return &conversationHTTP{
		service: conversation.NewService(store),
		logger:  slog.New(slog.NewTextHandler(io.Discard, nil)),
	}
}

func attachTestRequest(userID string, startingAfter int64) *http.Request {
	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/agent-runs/run-1/events?starting_after="+
			strconv.FormatInt(startingAfter, 10),
		nil,
	)
	request.SetPathValue("runID", "run-1")
	return request.WithContext(context.WithValue(
		request.Context(),
		sessionContextKey{},
		auth.Session{User: auth.User{ID: userID}},
	))
}

func attachPage(
	runStatus string,
	assistantStatus string,
	events []agent.Event,
) conversation.RunEventPage {
	lastSequence := int64(0)
	if len(events) > 0 {
		lastSequence = events[len(events)-1].Sequence
	}
	return conversation.RunEventPage{
		ExecutionID:     "execution-1",
		ProtocolVersion: agent.ProtocolVersion,
		RunStatus:       runStatus,
		AssistantStatus: assistantStatus,
		LastSequence:    lastSequence,
		Events:          events,
	}
}

func attachEvent(sequence int64, eventType string, data string) agent.Event {
	return agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     "execution-1",
		RunID:           "run-1",
		Sequence:        sequence,
		Type:            eventType,
		OccurredAt:      time.Now().UTC(),
		Data:            json.RawMessage(data),
	}
}
