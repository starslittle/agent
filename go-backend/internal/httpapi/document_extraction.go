package httpapi

import (
	"errors"
	"net/http"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/conversation"
	"github.com/starslittle/agent/go-backend/internal/documents"
	runsupervisor "github.com/starslittle/agent/go-backend/internal/runs"
)

type documentExtractionHTTP struct {
	documents  *documents.Service
	runs       *conversation.Service
	supervisor *runsupervisor.Supervisor
}

func newDocumentExtractionHTTP(documentsService *documents.Service, runService *conversation.Service, supervisor *runsupervisor.Supervisor) *documentExtractionHTTP {
	return &documentExtractionHTTP{documents: documentsService, runs: runService, supervisor: supervisor}
}

func (h *documentExtractionHTTP) create(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeJSONError(w, http.StatusBadRequest, "idempotency_key_required")
		return
	}
	document, err := h.documents.Document(r.Context(), session.User.ID, r.PathValue("documentID"))
	if err != nil {
		if errors.Is(err, documents.ErrNotFound) {
			writeJSONError(w, http.StatusNotFound, "document_not_found")
		} else {
			writeJSONError(w, http.StatusBadRequest, "document_extraction_invalid")
		}
		return
	}
	generation, err := h.runs.CreateDocumentExtractionRun(r.Context(), conversation.DocumentExtractionParams{
		UserID: session.User.ID, DocumentID: document.ID, RevisionID: document.CurrentRevisionID,
		ContentHash: document.ContentHash, Content: document.Content, IdempotencyKey: idempotencyKey,
		RequestID: r.Header.Get(requestIDHeader),
	})
	if err != nil {
		switch {
		case errors.Is(err, conversation.ErrInvalidInput):
			writeJSONError(w, http.StatusBadRequest, "document_extraction_limit_exceeded")
		case errors.Is(err, conversation.ErrGenerationActive):
			writeJSONError(w, http.StatusConflict, "document_extraction_active")
		case errors.Is(err, conversation.ErrIdempotencyConflict):
			writeJSONError(w, http.StatusConflict, "document_extraction_idempotency_conflict")
		default:
			writeJSONError(w, http.StatusInternalServerError, "internal_error")
		}
		return
	}
	if h.supervisor != nil {
		if err := h.supervisor.Submit(generation.Run.ID); err != nil {
			writeJSONError(w, http.StatusServiceUnavailable, "document_extraction_scheduler_unavailable")
			return
		}
	}
	status := http.StatusCreated
	if generation.Replayed {
		status = http.StatusOK
	}
	writePrivateJSON(w, status, map[string]any{
		"run_id": generation.Run.ID, "execution_id": generation.Run.ExecutionID,
		"conversation_id": generation.Conversation.ID, "status": generation.Run.Status,
		"run_purpose": conversation.DocumentExtractionPurpose, "document_id": document.ID,
		"document_revision_id": document.CurrentRevisionID,
		"events_url":           "/api/v1/agent-runs/" + generation.Run.ID + "/events",
		"replayed":             generation.Replayed,
	})
}
