package httpapi

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/documents"
)

type spaceHTTP struct {
	service         *documents.Service
	maxRequestBytes int64
}

type createFolderRequest struct {
	ParentID *string `json:"parent_id"`
	Name     string  `json:"name"`
}

type moveEntryRequest struct {
	ParentID        *string `json:"parent_id"`
	Name            string  `json:"name"`
	ExpectedVersion int64   `json:"expected_version"`
}

type createDocumentRequest struct {
	FolderID             string  `json:"folder_id"`
	Name                 string  `json:"name"`
	Content              string  `json:"content"`
	Source               string  `json:"source"`
	OriginalRelativePath *string `json:"original_relative_path"`
}

type updateDocumentRequest struct {
	Content         string `json:"content"`
	ExpectedVersion int64  `json:"expected_version"`
}

type deleteEntryRequest struct {
	ExpectedVersion int64  `json:"expected_version"`
	ConfirmName     string `json:"confirm_name"`
}

func newSpaceHTTP(service *documents.Service, maxRequestBytes int64) *spaceHTTP {
	return &spaceHTTP{service: service, maxRequestBytes: maxRequestBytes}
}

func (h *spaceHTTP) list(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var parentID *string
	if value := strings.TrimSpace(r.URL.Query().Get("parent_id")); value != "" {
		parentID = &value
	}
	limit, err := optionalInt(r.URL.Query().Get("limit"), 100)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_space_query")
		return
	}
	offset, err := optionalInt(r.URL.Query().Get("offset"), 0)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_space_query")
		return
	}
	items, err := h.service.List(r.Context(), session.User.ID, parentID, r.URL.Query().Get("sort"), limit, offset)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{
		"items": items, "limit": limit, "offset": offset,
		"has_more": len(items) == limit,
	})
}

func (h *spaceHTTP) folder(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	item, err := h.service.Folder(r.Context(), session.User.ID, r.PathValue("folderID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *spaceHTTP) breadcrumbs(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	items, err := h.service.Breadcrumbs(r.Context(), session.User.ID, r.PathValue("folderID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *spaceHTTP) createFolder(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input createFolderRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeJSONError(w, http.StatusBadRequest, "idempotency_key_required")
		return
	}
	item, err := h.service.CreateFolderWithID(r.Context(), session.User.ID, input.ParentID, input.Name, idempotencyKey)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusCreated, item)
}

func (h *spaceHTTP) moveFolder(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input moveEntryRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	item, err := h.service.MoveFolder(r.Context(), session.User.ID, r.PathValue("folderID"), input.ParentID, input.Name, input.ExpectedVersion)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *spaceHTTP) deleteFolder(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input deleteEntryRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	folder, err := h.service.Folder(r.Context(), session.User.ID, r.PathValue("folderID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	if input.ConfirmName != folder.Name {
		writeJSONError(w, http.StatusBadRequest, "confirmation_name_mismatch")
		return
	}
	if err := h.service.DeleteFolder(r.Context(), session.User.ID, folder.ID, input.ExpectedVersion); err != nil {
		h.writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *spaceHTTP) createDocument(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input createDocumentRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	if input.Source == "" {
		input.Source = documents.SourceManual
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeJSONError(w, http.StatusBadRequest, "idempotency_key_required")
		return
	}
	item, err := h.service.CreateDocumentWithID(r.Context(), session.User.ID, input.FolderID, input.Name, input.Content, input.Source, input.OriginalRelativePath, idempotencyKey)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusCreated, item)
}

func (h *spaceHTTP) document(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	item, err := h.service.Document(r.Context(), session.User.ID, r.PathValue("documentID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	_ = h.service.Touch(r.Context(), session.User.ID, item.ID)
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *spaceHTTP) updateDocument(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input updateDocumentRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	item, err := h.service.UpdateDocument(r.Context(), session.User.ID, r.PathValue("documentID"), input.Content, input.ExpectedVersion)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *spaceHTTP) moveDocument(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input moveEntryRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil || input.ParentID == nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	item, err := h.service.MoveDocument(r.Context(), session.User.ID, r.PathValue("documentID"), *input.ParentID, input.Name, input.ExpectedVersion)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, item)
}

func (h *spaceHTTP) deleteDocument(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input deleteEntryRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	document, err := h.service.Document(r.Context(), session.User.ID, r.PathValue("documentID"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	if input.ConfirmName != document.Name {
		writeJSONError(w, http.StatusBadRequest, "confirmation_name_mismatch")
		return
	}
	if err := h.service.DeleteDocument(r.Context(), session.User.ID, document.ID, input.ExpectedVersion); err != nil {
		h.writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *spaceHTTP) revisions(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, err := optionalInt(r.URL.Query().Get("limit"), 50)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_space_query")
		return
	}
	items, err := h.service.Revisions(r.Context(), session.User.ID, r.PathValue("documentID"), limit)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writePrivateJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *spaceHTTP) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, documents.ErrNotFound):
		writeJSONError(w, http.StatusNotFound, "space_entry_not_found")
	case errors.Is(err, documents.ErrNameConflict):
		writeJSONError(w, http.StatusConflict, "space_name_conflict")
	case errors.Is(err, documents.ErrVersionConflict):
		writeJSONError(w, http.StatusConflict, "space_version_conflict")
	case errors.Is(err, documents.ErrFolderNotEmpty):
		writeJSONError(w, http.StatusConflict, "folder_not_empty")
	case errors.Is(err, documents.ErrLimitExceeded):
		writeJSONError(w, http.StatusRequestEntityTooLarge, "space_limit_exceeded")
	case errors.Is(err, documents.ErrInvalidInput):
		writeJSONError(w, http.StatusBadRequest, "invalid_space_input")
	default:
		writeJSONError(w, http.StatusInternalServerError, "internal_error")
	}
}

func optionalInt(raw string, fallback int) (int, error) {
	if strings.TrimSpace(raw) == "" {
		return fallback, nil
	}
	return strconv.Atoi(raw)
}

func writePrivateJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, status, payload)
}
