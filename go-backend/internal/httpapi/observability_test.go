package httpapi

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

type observabilityRunStore struct {
	conversation.Store
	params conversation.ObservabilityRunListParams
	items  []conversation.RunSummary
	detail conversation.RunDetail
}

func (s *observabilityRunStore) ListObservableAgentRuns(
	_ context.Context,
	params conversation.ObservabilityRunListParams,
) ([]conversation.RunSummary, error) {
	s.params = params
	return s.items, nil
}

func (s *observabilityRunStore) FindObservableAgentRunDetail(
	_ context.Context,
	_ string,
) (conversation.RunDetail, error) {
	return s.detail, nil
}

type auditAuthStore struct {
	*memoryAuthStore
	audits   []auth.ObservabilityAccessAudit
	auditErr error
}

func (s *auditAuthStore) RecordObservabilityAccess(
	_ context.Context,
	audit auth.ObservabilityAccessAudit,
) error {
	if s.auditErr != nil {
		return s.auditErr
	}
	s.audits = append(s.audits, audit)
	return nil
}

func TestObservabilityRoutesDenyNormalUsers(t *testing.T) {
	runStore := &observabilityRunStore{}
	server := newObservabilityTestServer(t, auth.RoleUser, runStore, nil)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/internal/agent-runs", nil)
	authorizeTestRequest(request)
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden ||
		!strings.Contains(response.Body.String(), "observability_access_denied") {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestObservabilityAdminFiltersAndAuditsList(t *testing.T) {
	privateDetail := "private list error detail"
	runStore := &observabilityRunStore{items: []conversation.RunSummary{{
		ID:          "10000000-0000-4000-8000-000000000001",
		OwnerUserID: "20000000-0000-4000-8000-000000000001",
		StartedAt:   time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC),
		ErrorDetail: &privateDetail,
	}}}
	auditStore := &auditAuthStore{memoryAuthStore: newMemoryAuthStore()}
	server := newObservabilityTestServer(t, auth.RoleObservabilityAdmin, runStore, auditStore)
	request := httptest.NewRequest(
		http.MethodGet,
		"/api/v1/internal/agent-runs?user_id=20000000-0000-4000-8000-000000000001&skill=research&workflow=research_graph&model=auto&status=failed&error_code=tool_failed&from=2026-08-01T00:00:00Z&to=2026-08-02T00:00:00Z&limit=20",
		nil,
	)
	authorizeTestRequest(request)
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if runStore.params.Skill != "research" || runStore.params.Workflow != "research_graph" ||
		runStore.params.Model != "auto" || runStore.params.Status != "failed" ||
		runStore.params.ErrorCode != "tool_failed" || runStore.params.From == nil || runStore.params.To == nil {
		t.Fatalf("filters were not passed through: %#v", runStore.params)
	}
	if len(auditStore.audits) != 1 || auditStore.audits[0].Action != "agent_runs.list" ||
		auditStore.audits[0].Filters["skill"] != "research" {
		t.Fatalf("audit mismatch: %#v", auditStore.audits)
	}
	if strings.Contains(response.Body.String(), "filters") {
		t.Fatalf("audit metadata leaked into response: %s", response.Body.String())
	}
	if strings.Contains(response.Body.String(), privateDetail) {
		t.Fatalf("error detail leaked into list response: %s", response.Body.String())
	}
}

func TestObservabilityAdminDetailIsRedactedAndAudited(t *testing.T) {
	runID := "10000000-0000-4000-8000-000000000001"
	runStore := &observabilityRunStore{detail: conversation.RunDetail{
		Run: conversation.RunSummary{
			ID:          runID,
			OwnerUserID: "20000000-0000-4000-8000-000000000001",
			ErrorDetail: stringPointer("secret connection string"),
		},
		Spans: []conversation.RunSpan{{Attributes: json.RawMessage(`{"secret":"token"}`)}},
		Events: []conversation.RunEvent{
			{Type: "tool.completed", Data: json.RawMessage(`{"input":"private message"}`)},
			{Type: "artifact.created", Data: json.RawMessage(`{"artifact_id":"a1","artifact_type":"report","secret":"hidden"}`)},
		},
		Prompts: []conversation.RunPrompt{{PromptHash: "private-prompt-hash"}},
	}}
	auditStore := &auditAuthStore{memoryAuthStore: newMemoryAuthStore()}
	server := newObservabilityTestServer(t, auth.RoleObservabilityAdmin, runStore, auditStore)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/internal/agent-runs/"+runID, nil)
	authorizeTestRequest(request)
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	body := response.Body.String()
	for _, forbidden := range []string{"secret connection string", "private message", `"secret":"token"`, "private-prompt-hash", "hidden"} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("%q leaked in response: %s", forbidden, body)
		}
	}
	if !strings.Contains(body, `"artifact_id":"a1"`) || len(auditStore.audits) != 1 ||
		auditStore.audits[0].TargetRunID != runID {
		t.Fatalf("safe projection or audit missing: body=%s audits=%#v", body, auditStore.audits)
	}
}

func TestObservabilityAuditFailureDoesNotReturnRunData(t *testing.T) {
	runStore := &observabilityRunStore{items: []conversation.RunSummary{{ID: "sensitive-run"}}}
	auditStore := &auditAuthStore{
		memoryAuthStore: newMemoryAuthStore(),
		auditErr:        errors.New("audit unavailable"),
	}
	server := newObservabilityTestServer(t, auth.RoleObservabilityAdmin, runStore, auditStore)
	request := httptest.NewRequest(http.MethodGet, "/api/v1/internal/agent-runs", nil)
	authorizeTestRequest(request)
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusInternalServerError || strings.Contains(response.Body.String(), "sensitive-run") {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func newObservabilityTestServer(
	t *testing.T,
	role string,
	runStore conversation.Store,
	providedAuthStore *auditAuthStore,
) http.Handler {
	t.Helper()
	authStore := providedAuthStore
	if authStore == nil {
		authStore = &auditAuthStore{memoryAuthStore: newMemoryAuthStore()}
	}
	tokenHash := sha256.Sum256([]byte(testSessionToken))
	user := auth.User{
		ID:          "00000000-0000-4000-8000-000000000001",
		Email:       "observer@example.com",
		DisplayName: "Observer",
		Status:      "active",
		Role:        role,
		CreatedAt:   time.Now().UTC(),
	}
	authStore.users[user.ID] = auth.Credential{User: user}
	authStore.emails[user.Email] = user.ID
	authStore.sessions[string(tokenHash[:])] = auth.Session{
		ID:         "00000000-0000-4000-8000-000000000002",
		User:       user,
		CSRFToken:  testCSRFToken,
		CreatedAt:  time.Now().UTC(),
		LastSeenAt: time.Now().UTC(),
		ExpiresAt:  time.Now().Add(time.Hour).UTC(),
	}
	cfg := config.Config{
		AppEnv:                "test",
		PythonBaseURL:         "http://127.0.0.1:1",
		MaxRequestBytes:       1 << 20,
		UpstreamHeaderTimeout: time.Second,
		InternalAgentSecret:   "test-secret-that-is-at-least-32-characters",
	}
	server, err := New(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		auth.NewService(authStore, time.Hour),
		conversation.NewService(runStore),
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	return server.Handler()
}

func stringPointer(value string) *string { return &value }
