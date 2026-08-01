package httpapi

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/skills"
)

type fakeSkillCatalogClient struct {
	catalog skills.Catalog
	err     error
}

func (f fakeSkillCatalogClient) Skills(context.Context, string, string) (skills.Catalog, error) {
	return f.catalog, f.err
}

func visibleTestSkill(id string) skills.Skill {
	return skills.Skill{ID: id, Version: 1, Title: id, Description: "description", Command: "/" + id, PublicPurpose: "purpose", ConfirmationSummary: "confirmation", Available: true, Effective: true}
}

func authenticatedSkillRequest(method, path string) *http.Request {
	request := httptest.NewRequest(method, path, nil)
	request.Header.Set(requestIDHeader, "request-1")
	return request.WithContext(context.WithValue(request.Context(), sessionContextKey{}, auth.Session{User: auth.User{ID: "user-1"}}))
}

func TestSkillHTTPListsOnlyEffectiveProductSkills(t *testing.T) {
	handler := newSkillHTTP(fakeSkillCatalogClient{catalog: skills.Catalog{Items: []skills.Skill{visibleTestSkill("fortune"), visibleTestSkill("future_skill"), visibleTestSkill("research")}}})
	response := httptest.NewRecorder()
	handler.list(response, authenticatedSkillRequest(http.MethodGet, "/api/v1/skills"))
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), `"id":"research"`) || !strings.Contains(response.Body.String(), `"id":"fortune"`) || strings.Contains(response.Body.String(), "future_skill") {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestSkillHTTPUsesSafeUnavailableAndFailureStates(t *testing.T) {
	handler := newSkillHTTP(fakeSkillCatalogClient{catalog: skills.Catalog{Items: []skills.Skill{visibleTestSkill("research")}}})
	request := authenticatedSkillRequest(http.MethodGet, "/api/v1/skills/missing")
	request.SetPathValue("skillID", "missing")
	missing := httptest.NewRecorder()
	handler.detail(missing, request)
	if missing.Code != http.StatusNotFound || !strings.Contains(missing.Body.String(), "skill_not_available") {
		t.Fatalf("missing status=%d body=%s", missing.Code, missing.Body.String())
	}

	failureHandler := newSkillHTTP(fakeSkillCatalogClient{err: errors.New("secret upstream reason")})
	failure := httptest.NewRecorder()
	failureHandler.list(failure, authenticatedSkillRequest(http.MethodGet, "/api/v1/skills"))
	if failure.Code != http.StatusServiceUnavailable || !strings.Contains(failure.Body.String(), "skill_catalog_unavailable") || strings.Contains(failure.Body.String(), "secret") {
		t.Fatalf("failure status=%d body=%s", failure.Code, failure.Body.String())
	}
}
