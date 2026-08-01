package runs

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/agenttrace"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

var ErrNotStarted = errors.New("run supervisor is not started")

type Store interface {
	ClaimRun(context.Context, string, string, time.Time) (conversation.ClaimedRun, bool, error)
	ClaimNextRun(context.Context, string, time.Time) (conversation.ClaimedRun, bool, error)
	RenewRunLease(context.Context, string, conversation.RunLease, time.Time) error
	ReleaseRunLease(context.Context, string, conversation.RunLease) error
	History(context.Context, string, string) ([]conversation.Message, error)
	CheckpointOwned(
		context.Context,
		string,
		string,
		string,
		string,
		int64,
		conversation.RunLease,
	) error
	AdvanceSequenceOwned(
		context.Context,
		string,
		string,
		int64,
		conversation.RunLease,
	) error
	RecordEventOwned(
		context.Context,
		string,
		string,
		agent.Event,
		conversation.RunLease,
	) (bool, error)
	Finish(context.Context, conversation.FinishGenerationParams) (string, error)
	PrepareContextPackage(context.Context, string, string, string, agent.SkillResolution, contextpackage.Requirements) (contextpackage.Package, error)
	FindContextPackageByRun(context.Context, string, string) (contextpackage.Package, error)
}

type Options struct {
	OwnerID       string
	LeaseDuration time.Duration
	PollInterval  time.Duration
	RunDeadline   time.Duration
}

type Supervisor struct {
	store   Store
	client  agent.Client
	logger  *slog.Logger
	options Options

	mu      sync.Mutex
	ctx     context.Context
	cancel  context.CancelFunc
	started bool
	wg      sync.WaitGroup
}

func New(
	store Store,
	client agent.Client,
	logger *slog.Logger,
	options Options,
) *Supervisor {
	if options.OwnerID == "" {
		options.OwnerID = newOwnerID()
	}
	if options.LeaseDuration <= 0 {
		options.LeaseDuration = 30 * time.Second
	}
	if options.PollInterval <= 0 {
		options.PollInterval = 2 * time.Second
	}
	if options.RunDeadline <= 0 {
		options.RunDeadline = 5 * time.Minute
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Supervisor{
		store:   store,
		client:  client,
		logger:  logger,
		options: options,
	}
}

func (s *Supervisor) Start(parent context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.started {
		return nil
	}
	if s.store == nil || s.client == nil {
		return errors.New("run supervisor dependencies are required")
	}
	s.ctx, s.cancel = context.WithCancel(parent)
	s.started = true
	s.wg.Add(1)
	go s.recoveryLoop()
	return nil
}

func (s *Supervisor) Submit(runID string) error {
	s.mu.Lock()
	if !s.started || s.ctx == nil || s.ctx.Err() != nil {
		s.mu.Unlock()
		return ErrNotStarted
	}
	ctx := s.ctx
	s.wg.Add(1)
	s.mu.Unlock()
	go func() {
		defer s.wg.Done()
		s.claimAndExecute(ctx, runID)
	}()
	return nil
}

func (s *Supervisor) Close(ctx context.Context) error {
	s.mu.Lock()
	if !s.started {
		s.mu.Unlock()
		return nil
	}
	s.cancel()
	s.mu.Unlock()

	done := make(chan struct{})
	go func() {
		s.wg.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (s *Supervisor) recoveryLoop() {
	defer s.wg.Done()
	s.recoverAvailable(s.ctx)
	ticker := time.NewTicker(s.options.PollInterval)
	defer ticker.Stop()
	for {
		select {
		case <-s.ctx.Done():
			return
		case <-ticker.C:
			s.recoverAvailable(s.ctx)
		}
	}
}

func (s *Supervisor) recoverAvailable(ctx context.Context) {
	for index := 0; index < 32 && ctx.Err() == nil; index++ {
		claim, ok, err := s.store.ClaimNextRun(
			ctx,
			s.options.OwnerID,
			time.Now().UTC().Add(s.options.LeaseDuration),
		)
		if err != nil {
			s.logger.Error("claim active Agent Run", "error", err)
			return
		}
		if !ok {
			return
		}
		s.launchClaim(ctx, claim)
	}
}

func (s *Supervisor) claimAndExecute(ctx context.Context, runID string) {
	claim, ok, err := s.store.ClaimRun(
		ctx,
		runID,
		s.options.OwnerID,
		time.Now().UTC().Add(s.options.LeaseDuration),
	)
	if err != nil {
		s.logger.Error("claim Agent Run", "run_id", runID, "error", err)
		return
	}
	if !ok {
		return
	}
	s.executeClaim(ctx, claim)
}

func (s *Supervisor) launchClaim(ctx context.Context, claim conversation.ClaimedRun) {
	s.wg.Add(1)
	go func() {
		defer s.wg.Done()
		s.executeClaim(ctx, claim)
	}()
}

func (s *Supervisor) executeClaim(
	parent context.Context,
	claim conversation.ClaimedRun,
) {
	runCtx, cancelRun := context.WithTimeout(parent, s.options.RunDeadline)
	defer cancelRun()

	leaseLost := make(chan error, 1)
	go s.renewLease(runCtx, cancelRun, claim, leaseLost)

	err := s.consume(runCtx, claim)
	select {
	case leaseErr := <-leaseLost:
		if leaseErr != nil {
			err = leaseErr
		}
	default:
	}
	if err == nil || errors.Is(err, conversation.ErrRunLeaseLost) {
		return
	}
	if parent.Err() != nil {
		s.releaseClaim(claim)
		return
	}

	status := string(agent.StatusFailed)
	code := "supervisor_execution_failed"
	if errors.Is(runCtx.Err(), context.DeadlineExceeded) {
		status = string(agent.StatusTimedOut)
		code = "supervisor_deadline_exceeded"
		cancelCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		_, _ = s.client.Cancel(
			cancelCtx,
			claim.UserID,
			claim.Run.RequestID,
			claim.Run.ExecutionID,
		)
		cancel()
	}
	content := claim.Assistant.Content
	loadCtx, loadCancel := context.WithTimeout(context.Background(), 5*time.Second)
	if history, historyErr := s.store.History(
		loadCtx,
		claim.UserID,
		claim.Conversation.ID,
	); historyErr == nil {
		for _, message := range history {
			if message.ID == claim.Assistant.ID {
				content = message.Content
				break
			}
		}
	}
	loadCancel()
	finishCtx, finishCancel := context.WithTimeout(
		context.WithoutCancel(parent),
		5*time.Second,
	)
	defer finishCancel()
	_, finishErr := s.store.Finish(
		finishCtx,
		conversation.FinishGenerationParams{
			UserID:              claim.UserID,
			RunID:               claim.Run.ID,
			AssistantMessageID:  claim.Assistant.ID,
			Content:             content,
			Status:              status,
			ErrorCode:           code,
			ErrorDetail:         err.Error(),
			GenerationCompleted: time.Now().UTC(),
			Lease:               &claim.Lease,
		},
	)
	if finishErr != nil && !errors.Is(finishErr, conversation.ErrRunLeaseLost) {
		s.logger.Error(
			"finish failed Agent Run",
			"run_id", claim.Run.ID,
			"error", finishErr,
		)
	}
}

func (s *Supervisor) renewLease(
	ctx context.Context,
	cancel context.CancelFunc,
	claim conversation.ClaimedRun,
	result chan<- error,
) {
	interval := s.options.LeaseDuration / 3
	if interval < 100*time.Millisecond {
		interval = 100 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			err := s.store.RenewRunLease(
				ctx,
				claim.Run.ID,
				claim.Lease,
				time.Now().UTC().Add(s.options.LeaseDuration),
			)
			if err != nil {
				select {
				case result <- err:
				default:
				}
				cancel()
				return
			}
		}
	}
}

func (s *Supervisor) consume(
	ctx context.Context,
	claim conversation.ClaimedRun,
) error {
	history, err := s.store.History(
		ctx,
		claim.UserID,
		claim.Conversation.ID,
	)
	if err != nil {
		return fmt.Errorf("load history: %w", err)
	}
	messages := make([]agent.Message, 0, len(history))
	for _, message := range history {
		if message.ID == claim.UserMessage.ID ||
			message.ID == claim.Assistant.ID ||
			strings.TrimSpace(message.Content) == "" {
			continue
		}
		messages = append(messages, agent.Message{
			Role:    message.Role,
			Content: message.Content,
		})
	}

	resolution, contextPackage, err := s.resolveAndPrepare(ctx, claim, messages)
	if err != nil {
		return fmt.Errorf("prepare frozen route context: %w", err)
	}
	request := agent.RunRequest{
		ProtocolVersion:      agent.ProtocolVersion,
		ExecutionID:          claim.Run.ExecutionID,
		RunID:                claim.Run.ID,
		RequestID:            claim.Run.RequestID,
		IdempotencyKey:       claim.Run.IdempotencyKey,
		ConversationID:       claim.Conversation.ID,
		AgentName:            resolutionAgentName(resolution),
		ModelID:              resolution.ModelID,
		RequestedSkill:       resolution.RequestedSkill,
		ResolvedSkills:       resolution.ResolvedSkills,
		PrimarySkill:         resolution.PrimarySkill,
		SelectionSource:      &resolution.SelectionSource,
		ContextPackageID:     resolution.ContextPackageID,
		ContextPackage:       &contextPackage,
		SuggestedSkill:       resolution.SuggestedSkill,
		RouteConfidence:      resolution.Confidence,
		RouteRequiresConfirm: resolution.RequiresConfirm,
		RouteReasonCode:      resolution.ReasonCode,
		Query:                claim.UserMessage.Content,
		Messages:             messages,
		DeadlineMS:           s.options.RunDeadline.Milliseconds(),
		UserID:               claim.UserID,
	}

	if claim.PreviousStatus == string(agent.StatusCancelRequested) {
		_, _ = s.client.Cancel(
			ctx,
			claim.UserID,
			claim.Run.RequestID,
			claim.Run.ExecutionID,
		)
	}
	stream, err := s.openStream(ctx, claim, request)
	if err != nil {
		return s.reconcileOpenFailure(ctx, claim, err)
	}
	defer func() { _ = stream.Close() }()

	var (
		answer       strings.Builder
		firstTokenAt *time.Time
		lastSequence = claim.Run.LastSequence
		resumeCount  int
	)
	answer.WriteString(claim.Assistant.Content)

	for {
		event, nextErr := stream.Next()
		if errors.Is(nextErr, agent.ErrSequenceGap) {
			if resumeCount >= 2 {
				return fmt.Errorf(
					"event sequence gap after %d: received %d",
					lastSequence,
					event.Sequence,
				)
			}
			resumeCount++
			_ = stream.Close()
			stream, err = s.client.Resume(ctx, request, lastSequence)
			if err != nil {
				return fmt.Errorf("resume sequence gap: %w", err)
			}
			continue
		}
		if nextErr != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			reconciled, reconcileErr := s.tryReconcileSnapshot(
				ctx,
				claim,
				answer.String(),
				firstTokenAt,
			)
			if reconciled {
				return reconcileErr
			}
			if agent.IsStreamDone(nextErr) {
				return errors.New("runtime stream ended without terminal event")
			}
			return fmt.Errorf("read runtime event: %w", nextErr)
		}
		if event.Sequence <= lastSequence {
			continue
		}

		if shouldPersistAttachEvent(event.Type) {
			stored := event
			stored.Data = agenttrace.Sanitize(event.Data)
			if _, err := s.store.RecordEventOwned(
				ctx,
				claim.UserID,
				claim.Run.ID,
				stored,
				claim.Lease,
			); err != nil {
				return err
			}
		}

		var data map[string]any
		_ = json.Unmarshal(event.Data, &data)
		if event.Type == "answer.delta" {
			text, _ := data["text"].(string)
			if text != "" {
				answer.WriteString(text)
				if firstTokenAt == nil {
					now := time.Now().UTC()
					firstTokenAt = &now
				}
			}
			if err := s.store.CheckpointOwned(
				ctx,
				claim.UserID,
				claim.Run.ID,
				claim.Assistant.ID,
				answer.String(),
				event.Sequence,
				claim.Lease,
			); err != nil {
				return err
			}
		} else if !shouldPersistAttachEvent(event.Type) {
			if err := s.store.AdvanceSequenceOwned(
				ctx,
				claim.UserID,
				claim.Run.ID,
				event.Sequence,
				claim.Lease,
			); err != nil {
				return err
			}
		}
		lastSequence = event.Sequence

		switch event.Type {
		case "run.completed":
			if strings.TrimSpace(answer.String()) == "" {
				return s.finish(
					ctx,
					claim,
					"",
					string(agent.StatusFailed),
					"empty_agent_response",
					"Python Agent completed without an answer",
					firstTokenAt,
				)
			}
			return s.finish(
				ctx,
				claim,
				answer.String(),
				string(agent.StatusCompleted),
				"",
				"",
				firstTokenAt,
			)
		case "run.cancelled":
			return s.finish(
				ctx,
				claim,
				answer.String(),
				string(agent.StatusCancelled),
				"generation_cancelled",
				"",
				firstTokenAt,
			)
		case "run.failed", "run.timed_out":
			status := string(agent.StatusFailed)
			if event.Type == "run.timed_out" {
				status = string(agent.StatusTimedOut)
			}
			code, _ := data["code"].(string)
			message, _ := data["message"].(string)
			return s.finish(
				ctx,
				claim,
				answer.String(),
				status,
				code,
				message,
				firstTokenAt,
			)
		}
	}
}

func (s *Supervisor) resolveAndPrepare(ctx context.Context, claim conversation.ClaimedRun, messages []agent.Message) (agent.SkillResolution, contextpackage.Package, error) {
	if claim.Run.ContextPackageID != nil {
		pkg, err := s.store.FindContextPackageByRun(ctx, claim.UserID, claim.Run.ID)
		if err != nil {
			return agent.SkillResolution{}, contextpackage.Package{}, err
		}
		return resolutionFromRun(claim.Run), pkg, nil
	}
	routeCtx, cancelRoute := context.WithTimeout(ctx, 15*time.Second)
	defer cancelRoute()
	result, err := s.client.Resolve(routeCtx, agent.RouteRequest{
		ProtocolVersion: agent.ProtocolVersion, ExecutionID: claim.Run.ExecutionID,
		RunID: claim.Run.ID, RequestID: claim.Run.RequestID, AgentName: claim.Run.AgentName,
		ModelID: claim.Run.ModelID, RequestedSkill: claim.Run.RequestedSkill,
		Query: claim.UserMessage.Content, Messages: messages, UserID: claim.UserID,
	})
	if err != nil {
		return agent.SkillResolution{}, contextpackage.Package{}, err
	}
	result.Resolution.RouteUsage = result.RouteUsage
	pkg, err := s.store.PrepareContextPackage(ctx, claim.UserID, claim.Run.ID, newPackageID(), result.Resolution, result.Requirements)
	if err != nil {
		return agent.SkillResolution{}, contextpackage.Package{}, err
	}
	result.Resolution.ContextPackageID = &pkg.PackageID
	return result.Resolution, pkg, nil
}

func resolutionFromRun(run conversation.Run) agent.SkillResolution {
	resolved := []string{}
	_ = json.Unmarshal(run.ResolvedSkills, &resolved)
	source := "direct"
	if run.SelectionSource != nil {
		source = *run.SelectionSource
	}
	confidence := 1.0
	return agent.SkillResolution{ModelID: run.ModelID, RequestedSkill: run.RequestedSkill, ResolvedSkills: resolved, PrimarySkill: run.PrimarySkill, SelectionSource: source, ContextPackageID: run.ContextPackageID, Confidence: &confidence, ReasonCode: "pre_resolved", ModelSnapshot: json.RawMessage(`{"model_id":"auto"}`)}
}

func resolutionAgentName(resolution agent.SkillResolution) string {
	if resolution.PrimarySkill == nil {
		return conversation.DefaultAgent
	}
	return *resolution.PrimarySkill + "_agent"
}

func shouldPersistAttachEvent(eventType string) bool {
	return agenttrace.ShouldPersist(eventType) ||
		eventType == "answer.delta" || eventType == "progress"
}

func (s *Supervisor) openStream(
	ctx context.Context,
	claim conversation.ClaimedRun,
	request agent.RunRequest,
) (agent.EventStream, error) {
	if claim.PreviousStatus == string(agent.StatusQueued) {
		return s.client.Start(ctx, request)
	}
	return s.client.Resume(ctx, request, claim.Run.LastSequence)
}

func (s *Supervisor) reconcileOpenFailure(
	ctx context.Context,
	claim conversation.ClaimedRun,
	openErr error,
) error {
	reconciled, err := s.tryReconcileSnapshot(
		ctx,
		claim,
		claim.Assistant.Content,
		nil,
	)
	if reconciled {
		return err
	}
	return fmt.Errorf("open runtime stream: %w", openErr)
}

func (s *Supervisor) tryReconcileSnapshot(
	ctx context.Context,
	claim conversation.ClaimedRun,
	content string,
	firstTokenAt *time.Time,
) (bool, error) {
	snapshot, err := s.client.Get(
		ctx,
		claim.UserID,
		claim.Run.RequestID,
		claim.Run.ExecutionID,
	)
	if err != nil || !snapshot.Status.Terminal() {
		return false, nil
	}
	status := string(snapshot.Status)
	code := ""
	detail := ""
	if snapshot.Status != agent.StatusCompleted {
		code, _ = snapshot.Error["code"].(string)
		detail, _ = snapshot.Error["message"].(string)
		if code == "" {
			code = "runtime_reconciled"
		}
	}
	if snapshot.Status == agent.StatusCompleted &&
		strings.TrimSpace(content) == "" {
		status = string(agent.StatusFailed)
		code = "runtime_recovery_missing_answer"
	}
	return true, s.finish(
		ctx,
		claim,
		content,
		status,
		code,
		detail,
		firstTokenAt,
	)
}

func (s *Supervisor) finish(
	ctx context.Context,
	claim conversation.ClaimedRun,
	content string,
	status string,
	code string,
	detail string,
	firstTokenAt *time.Time,
) error {
	_, err := s.store.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              claim.UserID,
		RunID:               claim.Run.ID,
		AssistantMessageID:  claim.Assistant.ID,
		Content:             content,
		Status:              status,
		ErrorCode:           code,
		ErrorDetail:         detail,
		FirstTokenAt:        firstTokenAt,
		GenerationCompleted: time.Now().UTC(),
		Lease:               &claim.Lease,
	})
	return err
}

func (s *Supervisor) releaseClaim(claim conversation.ClaimedRun) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	err := s.store.ReleaseRunLease(ctx, claim.Run.ID, claim.Lease)
	if err != nil && !errors.Is(err, conversation.ErrRunLeaseLost) {
		s.logger.Warn("release Agent Run lease", "run_id", claim.Run.ID, "error", err)
	}
}

func newOwnerID() string {
	value := make([]byte, 12)
	if _, err := io.ReadFull(rand.Reader, value); err != nil {
		panic("crypto/rand unavailable")
	}
	return "go_" + hex.EncodeToString(value)
}

func newPackageID() string {
	value := make([]byte, 16)
	if _, err := io.ReadFull(rand.Reader, value); err != nil {
		panic("crypto/rand unavailable")
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", value[0:4], value[4:6], value[6:8], value[8:10], value[10:16])
}
