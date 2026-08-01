package httpapi

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/platform/postgres"
	"github.com/starslittle/agent/go-backend/internal/proposals"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func TestWikiProposalHTTPIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	store, err := postgres.Open(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	wikiService := wiki.NewService(store)
	cfg := config.Config{AppEnv: "test", PythonBaseURL: "http://127.0.0.1:1", MaxRequestBytes: 1 << 20, UpstreamHeaderTimeout: time.Second, SessionTTL: time.Hour, InternalAgentSecret: "test-secret-that-is-at-least-32-characters"}
	server, err := NewWithProductServices(cfg, slog.New(slog.NewTextHandler(io.Discard, nil)), auth.NewService(store, time.Hour), ProductServices{Wiki: wikiService})
	if err != nil {
		t.Fatal(err)
	}

	unauthorized := httptest.NewRecorder()
	server.Handler().ServeHTTP(unauthorized, httptest.NewRequest(http.MethodGet, "/api/v1/wiki-proposals", nil))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized status=%d", unauthorized.Code)
	}
	cookie, csrf := registerIntegrationUser(t, server)
	me := authenticatedRequest(http.MethodGet, "/api/v1/me", "", cookie, "")
	meResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(meResponse, me)
	var mePayload struct {
		User auth.User `json:"user"`
	}
	if json.Unmarshal(meResponse.Body.Bytes(), &mePayload) != nil {
		t.Fatal("decode current user")
	}
	proposal, err := wikiService.CreateProposal(ctx, proposals.CreateParams{ID: "88888888-8888-4888-8888-888888888888", UserID: mePayload.User.ID, ItemType: wiki.TypePersonalRule, Domain: "career", ProposedContent: "回答时优先结合项目经历", SourceType: wiki.SourceAIInferred, CreatedBy: wiki.ActorAgent})
	if err != nil {
		t.Fatal(err)
	}

	list := authenticatedRequest(http.MethodGet, "/api/v1/wiki-proposals?status=pending", "", cookie, "")
	listResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(listResponse, list)
	if listResponse.Code != http.StatusOK || !strings.Contains(listResponse.Body.String(), proposal.ID) {
		t.Fatalf("list status=%d body=%s", listResponse.Code, listResponse.Body.String())
	}
	withoutCSRF := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+proposal.ID+"/accept", `{}`, cookie, "")
	withoutCSRF.Header.Set("Idempotency-Key", "missing-csrf")
	withoutCSRFResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(withoutCSRFResponse, withoutCSRF)
	if withoutCSRFResponse.Code != http.StatusForbidden {
		t.Fatalf("missing csrf status=%d", withoutCSRFResponse.Code)
	}

	body := `{"final_content":"回答时优先结合我的真实项目经历"}`
	accept := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+proposal.ID+"/accept", body, cookie, csrf)
	accept.Header.Set("Idempotency-Key", "http-accept")
	acceptResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(acceptResponse, accept)
	if acceptResponse.Code != http.StatusOK {
		t.Fatalf("accept status=%d body=%s", acceptResponse.Code, acceptResponse.Body.String())
	}
	var accepted proposals.Resolution
	decodeHTTPJSON(t, acceptResponse, &accepted)
	if accepted.AppliedItemID == nil || accepted.Proposal.Status != proposals.StatusAccepted {
		t.Fatalf("accepted=%#v", accepted)
	}
	replay := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+proposal.ID+"/accept", body, cookie, csrf)
	replay.Header.Set("Idempotency-Key", "http-accept")
	replayResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(replayResponse, replay)
	var replayed proposals.Resolution
	decodeHTTPJSON(t, replayResponse, &replayed)
	if replayResponse.Code != http.StatusOK || !replayed.Replayed {
		t.Fatalf("replay status=%d result=%#v", replayResponse.Code, replayed)
	}

	otherCookie, _ := registerIntegrationUser(t, server)
	cross := authenticatedRequest(http.MethodGet, "/api/v1/wiki-proposals/"+proposal.ID, "", otherCookie, "")
	crossResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(crossResponse, cross)
	if crossResponse.Code != http.StatusNotFound {
		t.Fatalf("cross-user status=%d", crossResponse.Code)
	}
}
