package httpapi

import (
	"errors"
	"net/http"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

type wikiHTTP struct {
	service         *wiki.Service
	maxRequestBytes int64
}

type createWikiRequest struct {
	Type               string  `json:"type"`
	Domain             string  `json:"domain"`
	Status             string  `json:"status"`
	Content            string  `json:"content"`
	SourceType         string  `json:"source_type"`
	SourceReference    *string `json:"source_reference"`
	DocumentID         *string `json:"document_id"`
	DocumentRevisionID *string `json:"document_revision_id"`
}

type updateWikiRequest struct {
	Content         string `json:"content"`
	ExpectedVersion int64  `json:"expected_version"`
}

type wikiVersionRequest struct {
	ExpectedVersion int64  `json:"expected_version"`
	ConfirmContent  string `json:"confirm_content"`
}

func newWikiHTTP(service *wiki.Service, maxRequestBytes int64) *wikiHTTP {
	return &wikiHTTP{service: service, maxRequestBytes: maxRequestBytes}
}

func (h *wikiHTTP) list(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, err := optionalInt(r.URL.Query().Get("limit"), 50)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_wiki_query")
		return
	}
	offset, err := optionalInt(r.URL.Query().Get("offset"), 0)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_wiki_query")
		return
	}
	var documentID *string
	if raw := strings.TrimSpace(r.URL.Query().Get("document_id")); raw != "" {
		documentID = &raw
	}
	params := wiki.ListParams{
		UserID: session.User.ID, Domain: r.URL.Query().Get("domain"), Query: r.URL.Query().Get("q"),
		DocumentID: documentID, IncludeForgotten: r.URL.Query().Get("include_forgotten") == "true",
		Limit: limit, Offset: offset,
	}
	if raw := strings.TrimSpace(r.URL.Query().Get("status")); raw != "" {
		params.Statuses = strings.Split(raw, ",")
	}
	if raw := strings.TrimSpace(r.URL.Query().Get("type")); raw != "" {
		params.Types = strings.Split(raw, ",")
	}
	items, err := h.service.List(r.Context(), params)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"items": items, "limit": limit, "offset": offset, "has_more": len(items) == limit})
}

func (h *wikiHTTP) create(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input createWikiRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	if input.SourceType == "" {
		input.SourceType = wiki.SourceUserStated
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeJSONError(w, http.StatusBadRequest, "idempotency_key_required")
		return
	}
	detail, err := h.service.Create(r.Context(), wiki.CreateItemParams{
		ID: idempotencyKey, RevisionID: auth.NewID(), UserID: session.User.ID, Type: input.Type, Domain: input.Domain, Status: input.Status,
		Content: input.Content, CreatedBy: wiki.ActorUser,
		Source: wiki.SourceInput{Type: input.SourceType, Reference: input.SourceReference, DocumentID: input.DocumentID, DocumentRevisionID: input.DocumentRevisionID},
	})
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusCreated, detail)
}

func (h *wikiHTTP) detail(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	detail, err := h.service.Get(r.Context(), session.User.ID, r.PathValue("itemID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, detail)
}

func (h *wikiHTTP) update(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input updateWikiRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	detail, err := h.service.Update(r.Context(), wiki.UpdateItemParams{
		UserID: session.User.ID, ItemID: r.PathValue("itemID"), ExpectedVersion: input.ExpectedVersion,
		Content: input.Content, CreatedBy: wiki.ActorUser, Source: wiki.SourceInput{Type: wiki.SourceUserStated},
	})
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, detail)
}

func (h *wikiHTTP) changeStatus(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input wikiVersionRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	var item wiki.Item
	var err error
	switch r.PathValue("action") {
	case "outdated":
		item, err = h.service.MarkOutdated(r.Context(), session.User.ID, r.PathValue("itemID"), input.ExpectedVersion)
	case "forget":
		item, err = h.service.Forget(r.Context(), session.User.ID, r.PathValue("itemID"), input.ExpectedVersion)
	case "restore":
		item, err = h.service.Restore(r.Context(), session.User.ID, r.PathValue("itemID"), input.ExpectedVersion)
	default:
		writeJSONError(w, http.StatusNotFound, "wiki_action_not_found")
		return
	}
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *wikiHTTP) deletePermanently(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input wikiVersionRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	detail, err := h.service.Get(r.Context(), session.User.ID, r.PathValue("itemID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	if input.ConfirmContent != detail.Item.Content {
		writeJSONError(w, http.StatusBadRequest, "confirmation_content_mismatch")
		return
	}
	if err := h.service.DeletePermanently(r.Context(), session.User.ID, detail.Item.ID, input.ExpectedVersion); err != nil {
		h.writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *wikiHTTP) revisions(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, err := optionalInt(r.URL.Query().Get("limit"), 50)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_wiki_query")
		return
	}
	items, err := h.service.Revisions(r.Context(), session.User.ID, r.PathValue("itemID"), limit)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *wikiHTTP) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, wiki.ErrNotFound), errors.Is(err, wiki.ErrDeleted):
		writeJSONError(w, http.StatusNotFound, "wiki_item_not_found")
	case errors.Is(err, wiki.ErrVersionConflict):
		writeJSONError(w, http.StatusConflict, "wiki_version_conflict")
	case errors.Is(err, wiki.ErrAlreadyExists):
		writeJSONError(w, http.StatusConflict, "wiki_idempotency_conflict")
	case errors.Is(err, wiki.ErrInvalidState):
		writeJSONError(w, http.StatusConflict, "wiki_invalid_state")
	case errors.Is(err, wiki.ErrInvalidInput):
		writeJSONError(w, http.StatusBadRequest, "invalid_wiki_input")
	default:
		writeJSONError(w, http.StatusInternalServerError, "internal_error")
	}
}
