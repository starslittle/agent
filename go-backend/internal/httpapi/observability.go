package httpapi

import (
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

type observabilityHTTP struct {
	authService *auth.Service
	runService  *conversation.Service
}

func newObservabilityHTTP(
	authService *auth.Service,
	runService *conversation.Service,
) *observabilityHTTP {
	return &observabilityHTTP{authService: authService, runService: runService}
}

func (h *observabilityHTTP) runs(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	params, filters, err := observableRunListParams(r)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_observability_filter")
		return
	}
	items, err := h.runService.ListObservableRuns(r.Context(), params)
	if err != nil {
		h.writeError(w, err)
		return
	}
	if err := h.authService.RecordObservabilityAccess(
		r.Context(),
		auth.ObservabilityAccessAudit{
			ActorUserID: session.User.ID,
			Action:      "agent_runs.list",
			Filters:     filters,
		},
	); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "observability_audit_failed")
		return
	}
	var nextBefore *time.Time
	if len(items) == params.Limit {
		value := items[len(items)-1].StartedAt
		nextBefore = &value
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_before": nextBefore,
	})
}

func (h *observabilityHTTP) runDetail(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	runID := strings.TrimSpace(r.PathValue("runID"))
	detail, err := h.runService.ObservableRunDetail(r.Context(), runID)
	if err != nil {
		h.writeError(w, err)
		return
	}
	if err := h.authService.RecordObservabilityAccess(
		r.Context(),
		auth.ObservabilityAccessAudit{
			ActorUserID: session.User.ID,
			Action:      "agent_runs.detail",
			TargetRunID: runID,
			Filters:     map[string]string{},
		},
	); err != nil {
		writeJSONError(w, http.StatusInternalServerError, "observability_audit_failed")
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func observableRunListParams(
	r *http.Request,
) (conversation.ObservabilityRunListParams, map[string]string, error) {
	query := r.URL.Query()
	params := conversation.ObservabilityRunListParams{
		UserID:    query.Get("user_id"),
		Skill:     query.Get("skill"),
		Workflow:  query.Get("workflow"),
		Model:     query.Get("model"),
		Status:    query.Get("status"),
		ErrorCode: query.Get("error_code"),
	}
	params.Limit, _ = strconv.Atoi(query.Get("limit"))
	if params.Limit <= 0 {
		params.Limit = 30
	}
	if params.Limit > 100 {
		params.Limit = 100
	}
	for raw, destination := range map[string]**time.Time{
		"from": &params.From, "to": &params.To, "before": &params.Before,
	} {
		value := strings.TrimSpace(query.Get(raw))
		if value == "" {
			continue
		}
		parsed, err := time.Parse(time.RFC3339Nano, value)
		if err != nil {
			return params, nil, err
		}
		*destination = &parsed
	}
	filters := make(map[string]string)
	for _, key := range []string{
		"user_id", "skill", "workflow", "model", "status", "error_code", "from", "to", "before",
	} {
		if value := strings.TrimSpace(query.Get(key)); value != "" {
			filters[key] = value
		}
	}
	return params, filters, nil
}

func (h *observabilityHTTP) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, conversation.ErrNotFound):
		writeJSONError(w, http.StatusNotFound, "agent_run_not_found")
	case errors.Is(err, conversation.ErrInvalidInput):
		writeJSONError(w, http.StatusBadRequest, "invalid_observability_filter")
	default:
		writeJSONError(w, http.StatusInternalServerError, "internal_error")
	}
}
