package httpapi

import (
	"context"
	"net/http"

	"github.com/starslittle/agent/go-backend/internal/skills"
)

type skillCatalogClient interface {
	Skills(ctx context.Context, userID, requestID string) (skills.Catalog, error)
}

type skillHTTP struct {
	client skillCatalogClient
}

func newSkillHTTP(client skillCatalogClient) *skillHTTP { return &skillHTTP{client: client} }

func (h *skillHTTP) list(w http.ResponseWriter, r *http.Request) {
	catalog, ok := h.catalog(w, r)
	if !ok {
		return
	}
	writePrivateJSON(w, http.StatusOK, catalog)
}

func (h *skillHTTP) detail(w http.ResponseWriter, r *http.Request) {
	catalog, ok := h.catalog(w, r)
	if !ok {
		return
	}
	for _, skill := range catalog.Items {
		if skill.ID == r.PathValue("skillID") {
			writePrivateJSON(w, http.StatusOK, skill)
			return
		}
	}
	writeJSONError(w, http.StatusNotFound, "skill_not_available")
}

func (h *skillHTTP) catalog(w http.ResponseWriter, r *http.Request) (skills.Catalog, bool) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return skills.Catalog{}, false
	}
	upstream, err := h.client.Skills(r.Context(), session.User.ID, r.Header.Get(requestIDHeader))
	if err != nil {
		writeJSONError(w, http.StatusServiceUnavailable, "skill_catalog_unavailable")
		return skills.Catalog{}, false
	}
	catalog, err := skills.ValidateAndProject(upstream)
	if err != nil {
		writeJSONError(w, http.StatusServiceUnavailable, "skill_catalog_unavailable")
		return skills.Catalog{}, false
	}
	return catalog, true
}
