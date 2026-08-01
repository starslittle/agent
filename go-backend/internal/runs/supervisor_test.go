package runs

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func TestSupervisorRecoversRunningRunAfterRestart(t *testing.T) {
	store := newSupervisorStore(string(agent.StatusRunning), 2, "已有")
	client := &supervisorClient{
		resumeEvents: []agent.Event{
			testEvent(store.run, 3, "answer.delta", `{"text":"恢复"}`),
			testEvent(store.run, 4, "run.completed", `{}`),
		},
	}
	supervisor := New(
		store,
		client,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		Options{
			OwnerID:       "owner-restart",
			LeaseDuration: time.Second,
			PollInterval:  time.Hour,
			RunDeadline:   5 * time.Second,
		},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	if err := supervisor.Start(ctx); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	waitForFinish(t, store)
	closeSupervisor(t, supervisor)

	client.mu.Lock()
	startCalls := client.startCalls
	resumeCalls := client.resumeCalls
	startingAfter := client.startingAfter
	client.mu.Unlock()
	if startCalls != 0 || resumeCalls != 1 || startingAfter != 2 {
		t.Fatalf(
			"calls start=%d resume=%d starting_after=%d",
			startCalls,
			resumeCalls,
			startingAfter,
		)
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.finishCount != 1 ||
		store.finishedStatus != string(agent.StatusCompleted) ||
		store.finishedContent != "已有恢复" {
		t.Fatalf(
			"finish count=%d status=%q content=%q",
			store.finishCount,
			store.finishedStatus,
			store.finishedContent,
		)
	}
}

func TestDuplicateSupervisorClaimExecutesRunOnce(t *testing.T) {
	store := newSupervisorStore(string(agent.StatusQueued), 0, "")
	client := &supervisorClient{
		startEvents: []agent.Event{
			testEvent(store.run, 1, "run.started", `{}`),
			testEvent(store.run, 2, "answer.delta", `{"text":"唯一回答"}`),
			testEvent(store.run, 3, "run.completed", `{}`),
		},
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	first := New(store, client, logger, Options{
		OwnerID:       "owner-a",
		LeaseDuration: time.Second,
		PollInterval:  time.Hour,
		RunDeadline:   5 * time.Second,
	})
	second := New(store, client, logger, Options{
		OwnerID:       "owner-b",
		LeaseDuration: time.Second,
		PollInterval:  time.Hour,
		RunDeadline:   5 * time.Second,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	if err := first.Start(ctx); err != nil {
		t.Fatalf("first Start() error = %v", err)
	}
	if err := second.Start(ctx); err != nil {
		t.Fatalf("second Start() error = %v", err)
	}
	waitForFinish(t, store)
	closeSupervisor(t, first)
	closeSupervisor(t, second)

	client.mu.Lock()
	totalStarts := client.startCalls + client.resumeCalls
	client.mu.Unlock()
	store.mu.Lock()
	finishCount := store.finishCount
	recorded := append([]agent.Event(nil), store.recorded...)
	store.mu.Unlock()
	if totalStarts != 1 || finishCount != 1 {
		t.Fatalf("runtime starts=%d finishes=%d, want 1/1", totalStarts, finishCount)
	}
	if len(recorded) != 3 || recorded[1].Type != "answer.delta" {
		t.Fatalf("recorded events = %#v, want contiguous attach replay", recorded)
	}
}

func TestSupervisorReconcilesTerminalSnapshotWhenReplayEnds(t *testing.T) {
	store := newSupervisorStore(string(agent.StatusRunning), 4, "已经持久化")
	client := &supervisorClient{
		snapshot: agent.Snapshot{
			Status:       agent.StatusCompleted,
			LastSequence: 4,
		},
	}
	supervisor := New(
		store,
		client,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		Options{
			OwnerID:       "owner-reconcile",
			LeaseDuration: time.Second,
			PollInterval:  time.Hour,
			RunDeadline:   5 * time.Second,
		},
	)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	if err := supervisor.Start(ctx); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	waitForFinish(t, store)
	closeSupervisor(t, supervisor)

	store.mu.Lock()
	defer store.mu.Unlock()
	if store.finishCount != 1 ||
		store.finishedStatus != string(agent.StatusCompleted) ||
		store.finishedContent != "已经持久化" {
		t.Fatalf(
			"reconciled count=%d status=%q content=%q",
			store.finishCount,
			store.finishedStatus,
			store.finishedContent,
		)
	}
}

type supervisorStore struct {
	mu              sync.Mutex
	run             conversation.ClaimedRun
	claimed         bool
	terminal        bool
	finished        chan struct{}
	finishOnce      sync.Once
	finishCount     int
	finishedStatus  string
	finishedContent string
	recorded        []agent.Event
}

func (s *supervisorStore) PrepareContextPackage(_ context.Context, _ string, _ string, packageID string, resolution agent.SkillResolution, requirements contextpackage.Requirements) (contextpackage.Package, error) {
	pkg, err := contextpackage.Assemble(packageID, s.run.Run.ID, requirements, nil)
	if err != nil {
		return contextpackage.Package{}, err
	}
	s.run.Run.ContextPackageID = &pkg.PackageID
	s.run.Run.ModelID = resolution.ModelID
	s.run.Run.RequestedSkill = resolution.RequestedSkill
	encoded, _ := json.Marshal(resolution.ResolvedSkills)
	s.run.Run.ResolvedSkills = encoded
	s.run.Run.PrimarySkill = resolution.PrimarySkill
	s.run.Run.SelectionSource = &resolution.SelectionSource
	return pkg, nil
}
func (s *supervisorStore) FindContextPackageByRun(_ context.Context, _ string, _ string) (contextpackage.Package, error) {
	return contextpackage.Package{PackageID: *s.run.Run.ContextPackageID, Purpose: "conversation", Items: []contextpackage.Item{}}, nil
}

func newSupervisorStore(
	status string,
	lastSequence int64,
	content string,
) *supervisorStore {
	clientMessageID := "11111111-1111-4111-8111-111111111111"
	return &supervisorStore{
		run: conversation.ClaimedRun{
			Generation: conversation.Generation{
				Conversation: conversation.Conversation{
					ID:     "22222222-2222-4222-8222-222222222222",
					UserID: "33333333-3333-4333-8333-333333333333",
				},
				UserMessage: conversation.Message{
					ID:              "44444444-4444-4444-8444-444444444444",
					ClientMessageID: &clientMessageID,
					Role:            "user",
					Content:         "继续执行",
					Status:          "completed",
				},
				Assistant: conversation.Message{
					ID:      "55555555-5555-4555-8555-555555555555",
					Role:    "assistant",
					Content: content,
					Status:  "streaming",
				},
				Run: conversation.Run{
					ID:                 "66666666-6666-4666-8666-666666666666",
					ExecutionID:        "exec_test",
					IdempotencyKey:     clientMessageID,
					ConversationID:     "22222222-2222-4222-8222-222222222222",
					UserMessageID:      "44444444-4444-4444-8444-444444444444",
					AssistantMessageID: "55555555-5555-4555-8555-555555555555",
					RequestID:          "request-test",
					AgentName:          conversation.DefaultAgent,
					Status:             status,
					ProtocolVersion:    agent.ProtocolVersion,
					LastSequence:       lastSequence,
				},
			},
			UserID:         "33333333-3333-4333-8333-333333333333",
			PreviousStatus: status,
		},
		finished: make(chan struct{}),
	}
}

func (s *supervisorStore) ClaimRun(
	_ context.Context,
	runID string,
	ownerID string,
	expiresAt time.Time,
) (conversation.ClaimedRun, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if runID != s.run.Run.ID || s.claimed || s.terminal {
		return conversation.ClaimedRun{}, false, nil
	}
	return s.claim(ownerID, expiresAt), true, nil
}

func (s *supervisorStore) ClaimNextRun(
	_ context.Context,
	ownerID string,
	expiresAt time.Time,
) (conversation.ClaimedRun, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.claimed || s.terminal {
		return conversation.ClaimedRun{}, false, nil
	}
	return s.claim(ownerID, expiresAt), true, nil
}

func (s *supervisorStore) claim(
	ownerID string,
	expiresAt time.Time,
) conversation.ClaimedRun {
	s.claimed = true
	s.run.Lease = conversation.RunLease{
		OwnerID:   ownerID,
		Epoch:     s.run.Lease.Epoch + 1,
		ExpiresAt: expiresAt,
	}
	return s.run
}

func (s *supervisorStore) RenewRunLease(
	_ context.Context,
	runID string,
	lease conversation.RunLease,
	_ time.Time,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.owns(runID, lease) {
		return conversation.ErrRunLeaseLost
	}
	return nil
}

func (s *supervisorStore) ReleaseRunLease(
	_ context.Context,
	runID string,
	lease conversation.RunLease,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.owns(runID, lease) {
		return conversation.ErrRunLeaseLost
	}
	s.claimed = false
	return nil
}

func (s *supervisorStore) History(
	_ context.Context,
	_ string,
	_ string,
) ([]conversation.Message, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return []conversation.Message{s.run.UserMessage, s.run.Assistant}, nil
}

func (s *supervisorStore) CheckpointOwned(
	_ context.Context,
	_ string,
	runID string,
	_ string,
	content string,
	sequence int64,
	lease conversation.RunLease,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.owns(runID, lease) {
		return conversation.ErrRunLeaseLost
	}
	s.run.Assistant.Content = content
	s.run.Run.LastSequence = sequence
	return nil
}

func (s *supervisorStore) AdvanceSequenceOwned(
	_ context.Context,
	_ string,
	runID string,
	sequence int64,
	lease conversation.RunLease,
) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.owns(runID, lease) {
		return conversation.ErrRunLeaseLost
	}
	s.run.Run.LastSequence = sequence
	return nil
}

func (s *supervisorStore) RecordEventOwned(
	_ context.Context,
	_ string,
	runID string,
	event agent.Event,
	lease conversation.RunLease,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if !s.owns(runID, lease) {
		return false, conversation.ErrRunLeaseLost
	}
	s.run.Run.LastSequence = event.Sequence
	s.recorded = append(s.recorded, event)
	return true, nil
}

func (s *supervisorStore) Finish(
	_ context.Context,
	params conversation.FinishGenerationParams,
) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if params.Lease == nil || !s.owns(params.RunID, *params.Lease) {
		return "", conversation.ErrRunLeaseLost
	}
	s.finishCount++
	s.finishedStatus = params.Status
	s.finishedContent = params.Content
	s.terminal = true
	s.run.Run.Status = params.Status
	s.run.Assistant.Content = params.Content
	s.finishOnce.Do(func() { close(s.finished) })
	return params.Status, nil
}

func (s *supervisorStore) owns(
	runID string,
	lease conversation.RunLease,
) bool {
	return s.claimed &&
		runID == s.run.Run.ID &&
		lease.OwnerID == s.run.Lease.OwnerID &&
		lease.Epoch == s.run.Lease.Epoch
}

type supervisorClient struct {
	mu            sync.Mutex
	startEvents   []agent.Event
	resumeEvents  []agent.Event
	startCalls    int
	resumeCalls   int
	startingAfter int64
	snapshot      agent.Snapshot
	getErr        error
}

func (c *supervisorClient) Resolve(_ context.Context, request agent.RouteRequest) (agent.RouteResult, error) {
	confidence := 1.0
	resolution := agent.SkillResolution{ModelID: "auto", RequestedSkill: request.RequestedSkill, ResolvedSkills: []string{}, SelectionSource: "direct", Confidence: &confidence, ReasonCode: "general_conversation", ModelSnapshot: json.RawMessage(`{"model_id":"auto"}`)}
	return agent.RouteResult{Resolution: resolution, Requirements: contextpackage.Requirements{ExecutionMode: "direct", Purpose: "conversation", NeedsPersonalContext: false}}, nil
}

func (c *supervisorClient) Start(
	_ context.Context,
	_ agent.RunRequest,
) (agent.EventStream, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.startCalls++
	return &eventSliceStream{events: append([]agent.Event(nil), c.startEvents...)}, nil
}

func (c *supervisorClient) Resume(
	_ context.Context,
	_ agent.RunRequest,
	startingAfter int64,
) (agent.EventStream, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.resumeCalls++
	c.startingAfter = startingAfter
	return &eventSliceStream{events: append([]agent.Event(nil), c.resumeEvents...)}, nil
}

func (c *supervisorClient) Get(
	context.Context,
	string,
	string,
	string,
) (agent.Snapshot, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.getErr != nil {
		return agent.Snapshot{}, c.getErr
	}
	if c.snapshot.Status == "" {
		return agent.Snapshot{}, errors.New("unexpected Get")
	}
	return c.snapshot, nil
}

func (c *supervisorClient) Cancel(
	context.Context,
	string,
	string,
	string,
) (agent.Snapshot, error) {
	return agent.Snapshot{Status: agent.StatusCancelled}, nil
}

type eventSliceStream struct {
	events []agent.Event
	index  int
}

func (s *eventSliceStream) Next() (agent.Event, error) {
	if s.index >= len(s.events) {
		return agent.Event{}, io.EOF
	}
	event := s.events[s.index]
	s.index++
	return event, nil
}

func (s *eventSliceStream) Close() error {
	return nil
}

func testEvent(
	run conversation.ClaimedRun,
	sequence int64,
	eventType string,
	data string,
) agent.Event {
	return agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     run.Run.ExecutionID,
		RunID:           run.Run.ID,
		Sequence:        sequence,
		Type:            eventType,
		OccurredAt:      time.Now().UTC(),
		Data:            json.RawMessage(data),
	}
}

func waitForFinish(t *testing.T, store *supervisorStore) {
	t.Helper()
	select {
	case <-store.finished:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for supervisor finish")
	}
}

func closeSupervisor(t *testing.T, supervisor *Supervisor) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := supervisor.Close(ctx); err != nil {
		t.Fatalf("Close() error = %v", err)
	}
}
