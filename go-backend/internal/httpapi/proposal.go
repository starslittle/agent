package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/proposals"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

type proposalHTTP struct {
	service         *wiki.Service
	maxRequestBytes int64
}

type resolveProposalRequest struct {
	FinalContent *string `json:"final_content"`
}

func newProposalHTTP(service *wiki.Service, maxRequestBytes int64) *proposalHTTP {
	return &proposalHTTP{service: service, maxRequestBytes: maxRequestBytes}
}

func (h *proposalHTTP) list(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, err := optionalInt(r.URL.Query().Get("limit"), 50)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_proposal_query")
		return
	}
	offset, err := optionalInt(r.URL.Query().Get("offset"), 0)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_proposal_query")
		return
	}
	var documentID *string
	if value := strings.TrimSpace(r.URL.Query().Get("document_id")); value != "" {
		documentID = &value
	}
	runID := strings.TrimSpace(r.URL.Query().Get("run_id"))
	if len(runID) > 128 {
		writeJSONError(w, http.StatusBadRequest, "invalid_proposal_query")
		return
	}
	params := proposals.ListParams{UserID: session.User.ID, DocumentID: documentID, Limit: limit, Offset: offset}
	if runID != "" {
		params.Limit = 200
		params.Offset = 0
	}
	if value := strings.TrimSpace(r.URL.Query().Get("status")); value != "" {
		params.Statuses = strings.Split(value, ",")
	}
	items, err := h.service.Proposals(r.Context(), params)
	if err != nil {
		h.writeError(w, err)
		return
	}
	hasMore := len(items) == limit
	if runID != "" {
		filtered := make([]proposals.Proposal, 0, len(items))
		for _, item := range items {
			if proposalRunID(item) == runID {
				filtered = append(filtered, item)
			}
		}
		start := offset
		if start > len(filtered) {
			start = len(filtered)
		}
		end := start + limit
		if end > len(filtered) {
			end = len(filtered)
		}
		hasMore = end < len(filtered)
		items = filtered[start:end]
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"items": items, "limit": limit, "offset": offset, "has_more": hasMore})
}

func proposalRunID(proposal proposals.Proposal) string {
	if proposal.SourceDetail == nil {
		return ""
	}
	var detail struct {
		RunID       string `json:"run_id"`
		OriginRunID string `json:"origin_run_id"`
	}
	if json.Unmarshal([]byte(*proposal.SourceDetail), &detail) != nil {
		return ""
	}
	if strings.TrimSpace(detail.RunID) != "" {
		return strings.TrimSpace(detail.RunID)
	}
	return strings.TrimSpace(detail.OriginRunID)
}

func (h *proposalHTTP) detail(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	proposal, err := h.service.Proposal(r.Context(), session.User.ID, r.PathValue("proposalID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	var target any
	if proposal.TargetItemID != nil {
		detail, targetErr := h.service.Get(r.Context(), session.User.ID, *proposal.TargetItemID)
		if targetErr != nil {
			if !errors.Is(targetErr, wiki.ErrNotFound) && !errors.Is(targetErr, wiki.ErrDeleted) {
				h.writeError(w, targetErr)
				return
			}
		} else {
			target = detail
		}
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"proposal": proposal, "target": target})
}

func (h *proposalHTTP) resolve(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input resolveProposalRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeJSONError(w, http.StatusBadRequest, "idempotency_key_required")
		return
	}
	result, err := h.service.ResolveProposal(r.Context(), session.User.ID, r.PathValue("proposalID"), r.PathValue("action"), input.FinalContent, idempotencyKey)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, result)
}

func (h *proposalHTTP) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, proposals.ErrNotFound):
		writeJSONError(w, http.StatusNotFound, "wiki_proposal_not_found")
	case errors.Is(err, proposals.ErrVersionConflict):
		writeJSONError(w, http.StatusConflict, "wiki_proposal_target_conflict")
	case errors.Is(err, proposals.ErrInvalidState):
		writeJSONError(w, http.StatusConflict, "wiki_proposal_invalid_state")
	case errors.Is(err, proposals.ErrAlreadyExists), errors.Is(err, proposals.ErrIdempotencyConflict):
		writeJSONError(w, http.StatusConflict, "wiki_proposal_idempotency_conflict")
	case errors.Is(err, proposals.ErrInvalidInput):
		writeJSONError(w, http.StatusBadRequest, "invalid_wiki_proposal_input")
	default:
		writeJSONError(w, http.StatusInternalServerError, "internal_error")
	}
}
