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
	stringPointer := func(value string) *string { return &value }
	createProposal := func(id string, params proposals.CreateParams) proposals.Proposal {
		t.Helper()
		params.ID = id
		params.UserID = mePayload.User.ID
		params.CreatedBy = wiki.ActorAgent
		created, createErr := wikiService.CreateProposal(ctx, params)
		if createErr != nil {
			t.Fatal(createErr)
		}
		return created
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

	plain := createProposal("88888888-8888-4888-8888-888888888881", proposals.CreateParams{ItemType: wiki.TypeConfirmedFact, Domain: "career", ProposedContent: "已完成产品实习", SourceType: wiki.SourceAIInferred})
	plainAccept := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+plain.ID+"/accept", `{}`, cookie, csrf)
	plainAccept.Header.Set("Idempotency-Key", "http-accept-original")
	plainResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(plainResponse, plainAccept)
	var plainResolution proposals.Resolution
	decodeHTTPJSON(t, plainResponse, &plainResolution)
	if plainResponse.Code != http.StatusOK || plainResolution.AppliedItemID == nil || plainResolution.Proposal.FinalContent == nil || *plainResolution.Proposal.FinalContent != plain.ProposedContent {
		t.Fatalf("plain accept status=%d result=%#v", plainResponse.Code, plainResolution)
	}

	deferred := createProposal("88888888-8888-4888-8888-888888888882", proposals.CreateParams{ItemType: wiki.TypeCurrentState, Domain: "career", ProposedContent: "正在考虑转岗", SourceType: wiki.SourceAIInferred})
	deferRequest := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+deferred.ID+"/defer", `{}`, cookie, csrf)
	deferRequest.Header.Set("Idempotency-Key", "http-defer")
	deferResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(deferResponse, deferRequest)
	var deferredResolution proposals.Resolution
	decodeHTTPJSON(t, deferResponse, &deferredResolution)
	if deferResponse.Code != http.StatusOK || deferredResolution.Proposal.Status != proposals.StatusDeferred || deferredResolution.AppliedItemID != nil {
		t.Fatalf("defer status=%d result=%#v", deferResponse.Code, deferredResolution)
	}

	rejected := createProposal("88888888-8888-4888-8888-888888888883", proposals.CreateParams{ItemType: wiki.TypeAIAnalysis, Domain: "career", ProposedContent: "可能更适合管理路线", SourceType: wiki.SourceAIInferred})
	rejectRequest := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+rejected.ID+"/reject", `{}`, cookie, csrf)
	rejectRequest.Header.Set("Idempotency-Key", "http-reject")
	rejectResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(rejectResponse, rejectRequest)
	var rejectedResolution proposals.Resolution
	decodeHTTPJSON(t, rejectResponse, &rejectedResolution)
	if rejectResponse.Code != http.StatusOK || rejectedResolution.Proposal.Status != proposals.StatusRejected || rejectedResolution.AppliedItemID != nil {
		t.Fatalf("reject status=%d result=%#v", rejectResponse.Code, rejectedResolution)
	}

	runDetail := `{"run_id":"run-visible","source_excerpt":"原文片段"}`
	runProposal := createProposal("88888888-8888-4888-8888-888888888884", proposals.CreateParams{ItemType: wiki.TypeCurrentState, Domain: "career", ProposedContent: "正在准备面试", SourceType: wiki.SourceAIInferred, SourceDetail: &runDetail})
	runList := authenticatedRequest(http.MethodGet, "/api/v1/wiki-proposals?run_id=run-visible&limit=1", "", cookie, "")
	runListResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(runListResponse, runList)
	var runListPayload struct {
		Items   []proposals.Proposal `json:"items"`
		HasMore bool                 `json:"has_more"`
	}
	decodeHTTPJSON(t, runListResponse, &runListPayload)
	if runListResponse.Code != http.StatusOK || len(runListPayload.Items) != 1 || runListPayload.Items[0].ID != runProposal.ID || runListPayload.HasMore {
		t.Fatalf("run list status=%d payload=%#v", runListResponse.Code, runListPayload)
	}

	target, err := wikiService.Create(ctx, wiki.CreateItemParams{
		ID: "77777777-7777-4777-8777-777777777777", RevisionID: "66666666-6666-4666-8666-666666666666", UserID: mePayload.User.ID,
		Type: wiki.TypeCurrentState, Domain: "career", Content: "正在准备春招", Status: wiki.StatusConfirmed, ConfirmedByUser: true, CreatedBy: wiki.ActorUser,
		Source: wiki.SourceInput{ID: "55555555-5555-4555-8555-555555555555", Type: wiki.SourceUserStated},
	})
	if err != nil {
		t.Fatal(err)
	}
	updateProposal := createProposal("88888888-8888-4888-8888-888888888885", proposals.CreateParams{
		TargetItemID: &target.Item.ID, TargetRevisionID: &target.Revision.ID, ItemType: wiki.TypeCurrentState, Domain: "career",
		ProposedContent: "正在准备秋招", SourceType: wiki.SourceAIInferred, SourceReference: stringPointer("document review"),
	})
	detailRequest := authenticatedRequest(http.MethodGet, "/api/v1/wiki-proposals/"+updateProposal.ID, "", cookie, "")
	detailResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(detailResponse, detailRequest)
	var detailPayload struct {
		Proposal proposals.Proposal `json:"proposal"`
		Target   *wiki.ItemDetail   `json:"target"`
	}
	decodeHTTPJSON(t, detailResponse, &detailPayload)
	if detailResponse.Code != http.StatusOK || detailPayload.Target == nil || detailPayload.Target.Revision.Content != "正在准备春招" {
		t.Fatalf("detail status=%d payload=%#v", detailResponse.Code, detailPayload)
	}

	_, err = wikiService.Update(ctx, wiki.UpdateItemParams{
		ItemID: target.Item.ID, RevisionID: "66666666-6666-4666-8666-666666666667", UserID: mePayload.User.ID, ExpectedVersion: target.Item.Version,
		Content: "春招已经结束", CreatedBy: wiki.ActorUser, Source: wiki.SourceInput{ID: "55555555-5555-4555-8555-555555555556", Type: wiki.SourceUserStated},
	})
	if err != nil {
		t.Fatal(err)
	}
	conflictRequest := authenticatedRequest(http.MethodPost, "/api/v1/wiki-proposals/"+updateProposal.ID+"/accept", `{}`, cookie, csrf)
	conflictRequest.Header.Set("Idempotency-Key", "http-version-conflict")
	conflictResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(conflictResponse, conflictRequest)
	if conflictResponse.Code != http.StatusConflict || !strings.Contains(conflictResponse.Body.String(), "wiki_proposal_target_conflict") {
		t.Fatalf("conflict status=%d body=%s", conflictResponse.Code, conflictResponse.Body.String())
	}

	otherCookie, _ := registerIntegrationUser(t, server)
	cross := authenticatedRequest(http.MethodGet, "/api/v1/wiki-proposals/"+proposal.ID, "", otherCookie, "")
	crossResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(crossResponse, cross)
	if crossResponse.Code != http.StatusNotFound {
		t.Fatalf("cross-user status=%d", crossResponse.Code)
	}
}
