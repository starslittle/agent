package conversation

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
)

var ErrObservabilityUnavailable = errors.New("observability store unavailable")

func (s *Service) ListObservableRuns(
	ctx context.Context,
	params ObservabilityRunListParams,
) ([]RunSummary, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.Skill = strings.TrimSpace(params.Skill)
	params.Workflow = strings.TrimSpace(params.Workflow)
	params.Model = strings.TrimSpace(params.Model)
	params.Status = strings.TrimSpace(params.Status)
	params.ErrorCode = strings.TrimSpace(params.ErrorCode)
	if params.UserID != "" && !validUUID(params.UserID) {
		return nil, ErrInvalidInput
	}
	for _, value := range []string{
		params.Skill, params.Workflow, params.Model, params.ErrorCode,
	} {
		if len(value) > 200 {
			return nil, ErrInvalidInput
		}
	}
	if params.Status != "" && !validRunStatus(params.Status) {
		return nil, ErrInvalidInput
	}
	if params.From != nil && params.To != nil && params.From.After(*params.To) {
		return nil, ErrInvalidInput
	}
	if params.Limit <= 0 {
		params.Limit = 30
	}
	if params.Limit > 100 {
		params.Limit = 100
	}
	store, ok := s.store.(ObservabilityStore)
	if !ok {
		return nil, ErrObservabilityUnavailable
	}
	items, err := store.ListObservableAgentRuns(ctx, params)
	if err != nil {
		return nil, err
	}
	for index := range items {
		items[index].ErrorDetail = nil
	}
	return items, nil
}

func (s *Service) ObservableRunDetail(
	ctx context.Context,
	runID string,
) (RunDetail, error) {
	if !validUUID(strings.TrimSpace(runID)) {
		return RunDetail{}, ErrInvalidInput
	}
	store, ok := s.store.(ObservabilityStore)
	if !ok {
		return RunDetail{}, ErrObservabilityUnavailable
	}
	detail, err := store.FindObservableAgentRunDetail(ctx, runID)
	if err != nil {
		return detail, err
	}
	return redactObservableDetail(detail), nil
}

func validRunStatus(status string) bool {
	switch status {
	case "queued", "running", "cancel_requested", "completed", "cancelled", "failed", "timed_out":
		return true
	default:
		return false
	}
}

func validUUID(value string) bool {
	if len(value) == 36 {
		for _, index := range []int{8, 13, 18, 23} {
			if value[index] != '-' {
				return false
			}
		}
	} else if len(value) != 32 {
		return false
	}
	compact := strings.ReplaceAll(value, "-", "")
	if len(compact) != 32 {
		return false
	}
	_, err := hex.DecodeString(compact)
	return err == nil
}

func redactObservableDetail(detail RunDetail) RunDetail {
	detail.Run.ErrorDetail = nil
	detail.Prompts = []RunPrompt{}
	for index := range detail.Spans {
		detail.Spans[index].Attributes = json.RawMessage(`{}`)
	}
	for index := range detail.Events {
		detail.Events[index].Data = observableEventData(detail.Events[index])
	}
	return detail
}

func observableEventData(event RunEvent) json.RawMessage {
	var source map[string]any
	if err := json.Unmarshal(event.Data, &source); err != nil {
		return json.RawMessage(`{}`)
	}
	var keys []string
	switch event.Type {
	case "citation.created":
		keys = []string{"citation_id", "title", "url", "snippet", "source_type", "artifact_id", "sequence"}
	case "artifact.created":
		keys = []string{"artifact_id", "artifact_type", "media_type", "size_bytes"}
	default:
		return json.RawMessage(`{}`)
	}
	redacted := make(map[string]any, len(keys))
	for _, key := range keys {
		if value, ok := source[key]; ok {
			redacted[key] = value
		}
	}
	encoded, err := json.Marshal(redacted)
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return encoded
}
