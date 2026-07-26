package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/conversation"
	"github.com/starslittle/agent/go-backend/internal/platform/postgres"
)

func TestPersistentConversationStreamIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	store, err := postgres.Open(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	var (
		upstreamMu       sync.Mutex
		upstreamPayloads []upstreamConversationRequest
	)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload upstreamConversationRequest
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
			t.Errorf("decode upstream request: %v", err)
		}
		upstreamMu.Lock()
		upstreamPayloads = append(upstreamPayloads, payload)
		upstreamMu.Unlock()

		w.Header().Set("Content-Type", "text/event-stream")
		if payload.Query == "等待取消" {
			w.WriteHeader(http.StatusOK)
			w.(http.Flusher).Flush()
			<-r.Context().Done()
			return
		}
		_, _ = io.WriteString(w, "event: message\n")
		_, _ = io.WriteString(w, `data: {"type":"delta","data":"Step1: 处理中\n","isThinking":true,"thinkingFinished":false}`+"\n\n")
		_, _ = io.WriteString(w, "event: message\n")
		_, _ = io.WriteString(w, `data: {"type":"delta","data":"你好","isThinking":false,"thinkingFinished":true}`+"\n\n")
		_, _ = io.WriteString(w, "event: message\n")
		_, _ = io.WriteString(w, `data: {"type":"done"}`+"\n\n")
	}))
	defer upstream.Close()

	cfg := config.Config{
		AppEnv:                "test",
		HTTPAddr:              ":0",
		PythonBaseURL:         upstream.URL,
		MaxRequestBytes:       1 << 20,
		UpstreamHeaderTimeout: 2 * time.Second,
		ShutdownTimeout:       time.Second,
		SessionTTL:            time.Hour,
		InternalAgentSecret:   "test-secret-that-is-at-least-32-characters",
	}
	authService := auth.NewService(store, time.Hour)
	conversationService := conversation.NewService(store)
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server, err := New(cfg, logger, authService, conversationService)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	registerBody := `{
		"email":"persistent-chat@example.com",
		"password":"a secure password for integration",
		"display_name":"持久化测试"
	}`
	register := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/auth/register",
		strings.NewReader(registerBody),
	)
	register.Header.Set("Content-Type", "application/json")
	registerResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(registerResponse, register)
	if registerResponse.Code != http.StatusCreated {
		t.Fatalf("register status = %d, body = %s", registerResponse.Code, registerResponse.Body.String())
	}
	var authPayload struct {
		CSRFToken string `json:"csrf_token"`
	}
	if err := json.Unmarshal(registerResponse.Body.Bytes(), &authPayload); err != nil {
		t.Fatalf("decode auth response: %v", err)
	}
	cookies := registerResponse.Result().Cookies()
	if len(cookies) == 0 {
		t.Fatal("register did not set a session cookie")
	}

	create := authenticatedRequest(
		http.MethodPost,
		"/api/v1/conversations",
		`{"agent_name":"default_llm_agent"}`,
		cookies[0],
		authPayload.CSRFToken,
	)
	createResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(createResponse, create)
	if createResponse.Code != http.StatusCreated {
		t.Fatalf("create status = %d, body = %s", createResponse.Code, createResponse.Body.String())
	}
	var created conversation.Conversation
	if err := json.Unmarshal(createResponse.Body.Bytes(), &created); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}

	for index, content := range []string{"第一条问题", "第二条问题"} {
		body, _ := json.Marshal(map[string]string{
			"content":           content,
			"client_message_id": auth.NewID(),
			"agent_name":        "default_llm_agent",
		})
		stream := authenticatedRequest(
			http.MethodPost,
			"/api/v1/conversations/"+created.ID+"/messages/stream",
			string(body),
			cookies[0],
			authPayload.CSRFToken,
		)
		stream.Header.Set(requestIDHeader, auth.NewID())
		streamResponse := httptest.NewRecorder()
		server.Handler().ServeHTTP(streamResponse, stream)
		if streamResponse.Code != http.StatusOK {
			t.Fatalf("stream %d status = %d, body = %s", index, streamResponse.Code, streamResponse.Body.String())
		}
		if !strings.Contains(streamResponse.Body.String(), `"type":"meta"`) ||
			!strings.Contains(streamResponse.Body.String(), `"type":"done"`) {
			t.Fatalf("stream %d missing lifecycle frames: %s", index, streamResponse.Body.String())
		}
	}

	messagesRequest := authenticatedRequest(
		http.MethodGet,
		"/api/v1/conversations/"+created.ID+"/messages?limit=50",
		"",
		cookies[0],
		"",
	)
	messagesResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(messagesResponse, messagesRequest)
	if messagesResponse.Code != http.StatusOK {
		t.Fatalf("messages status = %d, body = %s", messagesResponse.Code, messagesResponse.Body.String())
	}
	var messagesPayload struct {
		Items []conversation.Message `json:"items"`
	}
	if err := json.Unmarshal(messagesResponse.Body.Bytes(), &messagesPayload); err != nil {
		t.Fatalf("decode messages response: %v", err)
	}
	if len(messagesPayload.Items) != 4 {
		t.Fatalf("message count = %d, want 4", len(messagesPayload.Items))
	}
	for _, message := range messagesPayload.Items {
		if message.Role == "assistant" && message.Content != "你好" {
			t.Fatalf("thinking text leaked into persisted assistant content: %q", message.Content)
		}
	}

	runsRequest := authenticatedRequest(
		http.MethodGet,
		"/api/v1/agent-runs?limit=10&status=completed",
		"",
		cookies[0],
		"",
	)
	runsResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(runsResponse, runsRequest)
	if runsResponse.Code != http.StatusOK {
		t.Fatalf(
			"runs status = %d, body = %s",
			runsResponse.Code,
			runsResponse.Body.String(),
		)
	}
	var runsPayload struct {
		Items []conversation.RunSummary `json:"items"`
	}
	if err := json.Unmarshal(runsResponse.Body.Bytes(), &runsPayload); err != nil {
		t.Fatalf("decode runs response: %v", err)
	}
	if len(runsPayload.Items) != 2 {
		t.Fatalf("completed run count = %d, want 2", len(runsPayload.Items))
	}
	detailRequest := authenticatedRequest(
		http.MethodGet,
		"/api/v1/agent-runs/"+runsPayload.Items[0].ID,
		"",
		cookies[0],
		"",
	)
	detailResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(detailResponse, detailRequest)
	if detailResponse.Code != http.StatusOK {
		t.Fatalf(
			"run detail status = %d, body = %s",
			detailResponse.Code,
			detailResponse.Body.String(),
		)
	}

	liveGateway := httptest.NewServer(server.Handler())
	cancelCtx, cancelStream := context.WithCancel(context.Background())
	cancelBody, _ := json.Marshal(map[string]string{
		"content":           "等待取消",
		"client_message_id": auth.NewID(),
		"agent_name":        "default_llm_agent",
	})
	cancelRequest, err := http.NewRequestWithContext(
		cancelCtx,
		http.MethodPost,
		liveGateway.URL+"/api/v1/conversations/"+created.ID+"/messages/stream",
		bytes.NewReader(cancelBody),
	)
	if err != nil {
		t.Fatalf("create cancellation request: %v", err)
	}
	cancelRequest.Header.Set("Content-Type", "application/json")
	cancelRequest.Header.Set("X-CSRF-Token", authPayload.CSRFToken)
	cancelRequest.Header.Set(requestIDHeader, auth.NewID())
	cancelRequest.AddCookie(cookies[0])
	cancelResponse, err := http.DefaultClient.Do(cancelRequest)
	if err != nil {
		t.Fatalf("start cancellation request: %v", err)
	}
	cancelStream()
	_ = cancelResponse.Body.Close()
	liveGateway.Close()

	var stopped bool
	for attempt := 0; attempt < 20; attempt++ {
		request := authenticatedRequest(
			http.MethodGet,
			"/api/v1/conversations/"+created.ID+"/messages?limit=50",
			"",
			cookies[0],
			"",
		)
		response := httptest.NewRecorder()
		server.Handler().ServeHTTP(response, request)
		var payload struct {
			Items []conversation.Message `json:"items"`
		}
		_ = json.Unmarshal(response.Body.Bytes(), &payload)
		if len(payload.Items) == 6 &&
			payload.Items[len(payload.Items)-1].Status == "stopped" {
			stopped = true
			break
		}
		time.Sleep(25 * time.Millisecond)
	}
	if !stopped {
		t.Fatal("cancelled stream was not persisted as stopped")
	}

	upstreamMu.Lock()
	defer upstreamMu.Unlock()
	if len(upstreamPayloads) != 3 {
		t.Fatalf("upstream request count = %d", len(upstreamPayloads))
	}
	if len(upstreamPayloads[0].ChatHistory) != 0 {
		t.Fatalf("first request history = %#v", upstreamPayloads[0].ChatHistory)
	}
	if len(upstreamPayloads[1].ChatHistory) != 2 {
		t.Fatalf("second request history = %#v", upstreamPayloads[1].ChatHistory)
	}
	if len(upstreamPayloads[2].ChatHistory) != 4 {
		t.Fatalf("cancelled request history = %#v", upstreamPayloads[2].ChatHistory)
	}
}

func TestV1SequenceGapReplaysOrFailsClosedIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	store, err := postgres.Open(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	var (
		callsMu     sync.Mutex
		streamCalls = map[string][]int64{}
	)
	upstream := httptest.NewServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		r *http.Request,
	) {
		if r.Method == http.MethodDelete {
			executionID := r.Header.Get("X-Qidian-Execution-ID")
			writeJSON(w, http.StatusAccepted, map[string]any{
				"protocol_version": 1,
				"service_version":  "test",
				"execution_id":     executionID,
				"run_id":           "cancelled-upstream",
				"status":           "cancelled",
				"last_sequence":    3,
				"expires_at":       time.Now().UTC().Add(time.Minute),
			})
			return
		}
		if r.Method != http.MethodPost ||
			r.URL.Path != "/internal/v1/agent-runs:stream" {
			writeJSONError(w, http.StatusNotFound, "not_found")
			return
		}
		var run agent.RunRequest
		if err := json.NewDecoder(r.Body).Decode(&run); err != nil {
			t.Errorf("decode V1 run: %v", err)
			writeJSONError(w, http.StatusBadRequest, "invalid_run")
			return
		}
		startingAfter, _ := strconv.ParseInt(
			r.URL.Query().Get("starting_after"),
			10,
			64,
		)
		callsMu.Lock()
		streamCalls[run.Query] = append(streamCalls[run.Query], startingAfter)
		callsMu.Unlock()

		if run.Query == "不可恢复缺口" && startingAfter > 0 {
			writeJSONError(w, http.StatusServiceUnavailable, "replay_unavailable")
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		if startingAfter == 0 {
			writeV1TestEvent(t, w, run, 1, "run.started", `{}`)
			writeV1TestEvent(
				t,
				w,
				run,
				3,
				"answer.delta",
				`{"text":"答案"}`,
			)
			return
		}
		if run.Query == "回放提前结束" {
			writeV1TestEvent(
				t,
				w,
				run,
				2,
				"answer.delta",
				`{"text":"只有部分"}`,
			)
			return
		}
		writeV1TestEvent(
			t,
			w,
			run,
			2,
			"answer.delta",
			`{"text":"完整"}`,
		)
		writeV1TestEvent(
			t,
			w,
			run,
			3,
			"answer.delta",
			`{"text":"答案"}`,
		)
		writeV1TestEvent(t, w, run, 4, "run.completed", `{}`)
	}))
	defer upstream.Close()

	cfg := config.Config{
		AppEnv:                "test",
		PythonBaseURL:         upstream.URL,
		MaxRequestBytes:       1 << 20,
		UpstreamHeaderTimeout: 2 * time.Second,
		SessionTTL:            time.Hour,
		InternalAgentSecret:   "test-secret-that-is-at-least-32-characters",
		AgentProtocolMode:     "v1",
		AgentRunDeadline:      time.Minute,
		AgentCancelTimeout:    2 * time.Second,
		AgentReconcileTimeout: 2 * time.Second,
	}
	authService := auth.NewService(store, time.Hour)
	conversationService := conversation.NewService(store)
	server, err := New(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		authService,
		conversationService,
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	cookie, csrfToken := registerIntegrationUser(t, server)

	recovered := createAndStreamIntegrationMessage(
		t,
		server,
		cookie,
		csrfToken,
		"可恢复缺口",
	)
	if recovered.StreamStatus != http.StatusOK ||
		!strings.Contains(recovered.StreamBody, "完整") ||
		!strings.Contains(recovered.StreamBody, "答案") ||
		!strings.Contains(recovered.StreamBody, `"type":"done"`) {
		t.Fatalf("recovered stream was incomplete: %s", recovered.StreamBody)
	}
	recoveredMessages := getIntegrationMessages(
		t,
		server,
		cookie,
		recovered.ConversationID,
	)
	if got := recoveredMessages[len(recoveredMessages)-1]; got.Status != "completed" ||
		got.Content != "完整答案" {
		t.Fatalf("recovered assistant message = %#v", got)
	}
	recoveredRun := getIntegrationRun(
		t,
		server,
		cookie,
		recovered.ConversationID,
	)
	if recoveredRun.Status != "completed" {
		t.Fatalf("recovered run status = %q", recoveredRun.Status)
	}

	failed := createAndStreamIntegrationMessage(
		t,
		server,
		cookie,
		csrfToken,
		"不可恢复缺口",
	)
	if failed.StreamStatus != http.StatusOK ||
		!strings.Contains(failed.StreamBody, `"type":"error"`) ||
		strings.Contains(failed.StreamBody, `"type":"done"`) {
		t.Fatalf("unrecoverable stream did not fail closed: %s", failed.StreamBody)
	}
	failedMessages := getIntegrationMessages(
		t,
		server,
		cookie,
		failed.ConversationID,
	)
	if got := failedMessages[len(failedMessages)-1]; got.Status != "failed" ||
		got.Content != "" {
		t.Fatalf("failed assistant message retained partial content: %#v", got)
	}
	failedRun := getIntegrationRun(
		t,
		server,
		cookie,
		failed.ConversationID,
	)
	if failedRun.Status != "failed" ||
		failedRun.ErrorCode == nil ||
		*failedRun.ErrorCode != "agent_event_sequence_gap" {
		t.Fatalf("unrecoverable run did not fail closed: %#v", failedRun)
	}

	truncatedReplay := createAndStreamIntegrationMessage(
		t,
		server,
		cookie,
		csrfToken,
		"回放提前结束",
	)
	if !strings.Contains(truncatedReplay.StreamBody, `"type":"error"`) ||
		strings.Contains(truncatedReplay.StreamBody, `"type":"done"`) {
		t.Fatalf(
			"truncated replay did not fail closed: %s",
			truncatedReplay.StreamBody,
		)
	}
	truncatedMessages := getIntegrationMessages(
		t,
		server,
		cookie,
		truncatedReplay.ConversationID,
	)
	if got := truncatedMessages[len(truncatedMessages)-1]; got.Status != "failed" ||
		got.Content != "" {
		t.Fatalf("truncated replay retained partial content: %#v", got)
	}

	callsMu.Lock()
	defer callsMu.Unlock()
	if got := streamCalls["可恢复缺口"]; len(got) != 2 ||
		got[0] != 0 || got[1] != 1 {
		t.Fatalf("recoverable replay calls = %#v, want [0 1]", got)
	}
	if got := streamCalls["不可恢复缺口"]; len(got) != 3 ||
		got[0] != 0 || got[1] != 1 || got[2] != 1 {
		t.Fatalf("failed replay calls = %#v, want [0 1 1]", got)
	}
	if got := streamCalls["回放提前结束"]; len(got) != 2 ||
		got[0] != 0 || got[1] != 1 {
		t.Fatalf("truncated replay calls = %#v, want [0 1]", got)
	}
}

type integrationStreamResult struct {
	ConversationID string
	StreamStatus   int
	StreamBody     string
}

func registerIntegrationUser(
	t *testing.T,
	server *Server,
) (*http.Cookie, string) {
	t.Helper()
	email := auth.NewID() + "@example.com"
	register := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/auth/register",
		strings.NewReader(fmt.Sprintf(
			`{"email":%q,"password":"integration password 123","display_name":"replay"}`,
			email,
		)),
	)
	register.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, register)
	if response.Code != http.StatusCreated {
		t.Fatalf("register status = %d: %s", response.Code, response.Body.String())
	}
	var payload struct {
		CSRFToken string `json:"csrf_token"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode registration: %v", err)
	}
	cookies := response.Result().Cookies()
	if len(cookies) == 0 {
		t.Fatal("registration did not return a session cookie")
	}
	return cookies[0], payload.CSRFToken
}

func createAndStreamIntegrationMessage(
	t *testing.T,
	server *Server,
	cookie *http.Cookie,
	csrfToken string,
	content string,
) integrationStreamResult {
	t.Helper()
	create := authenticatedRequest(
		http.MethodPost,
		"/api/v1/conversations",
		`{"agent_name":"default_llm_agent"}`,
		cookie,
		csrfToken,
	)
	createResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(createResponse, create)
	if createResponse.Code != http.StatusCreated {
		t.Fatalf("create conversation: %s", createResponse.Body.String())
	}
	var item conversation.Conversation
	if err := json.Unmarshal(createResponse.Body.Bytes(), &item); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	body, _ := json.Marshal(map[string]string{
		"content":           content,
		"client_message_id": auth.NewID(),
		"agent_name":        "default_llm_agent",
	})
	request := authenticatedRequest(
		http.MethodPost,
		"/api/v1/conversations/"+item.ID+"/messages/stream",
		string(body),
		cookie,
		csrfToken,
	)
	request.Header.Set(requestIDHeader, auth.NewID())
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	return integrationStreamResult{
		ConversationID: item.ID,
		StreamStatus:   response.Code,
		StreamBody:     response.Body.String(),
	}
}

func getIntegrationMessages(
	t *testing.T,
	server *Server,
	cookie *http.Cookie,
	conversationID string,
) []conversation.Message {
	t.Helper()
	request := authenticatedRequest(
		http.MethodGet,
		"/api/v1/conversations/"+conversationID+"/messages?limit=50",
		"",
		cookie,
		"",
	)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("get messages: %s", response.Body.String())
	}
	var payload struct {
		Items []conversation.Message `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode messages: %v", err)
	}
	return payload.Items
}

func getIntegrationRun(
	t *testing.T,
	server *Server,
	cookie *http.Cookie,
	conversationID string,
) conversation.RunSummary {
	t.Helper()
	request := authenticatedRequest(
		http.MethodGet,
		"/api/v1/agent-runs?limit=100",
		"",
		cookie,
		"",
	)
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("get runs: %s", response.Body.String())
	}
	var payload struct {
		Items []conversation.RunSummary `json:"items"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode runs: %v", err)
	}
	for _, item := range payload.Items {
		if item.ConversationID == conversationID {
			return item
		}
	}
	t.Fatalf("run for conversation %s was not found", conversationID)
	return conversation.RunSummary{}
}

func writeV1TestEvent(
	t *testing.T,
	w io.Writer,
	run agent.RunRequest,
	sequence int64,
	eventType string,
	data string,
) {
	t.Helper()
	event := agent.Event{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     run.ExecutionID,
		RunID:           run.RunID,
		Sequence:        sequence,
		Type:            eventType,
		OccurredAt:      time.Now().UTC(),
		Data:            json.RawMessage(data),
	}
	encoded, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = fmt.Fprintf(
		w,
		"event: %s\nid: %s\ndata: %s\n\n",
		event.Type,
		event.SSEID(),
		encoded,
	)
}

func authenticatedRequest(
	method string,
	path string,
	body string,
	cookie *http.Cookie,
	csrfToken string,
) *http.Request {
	var reader io.Reader
	if body != "" {
		reader = bytes.NewBufferString(body)
	}
	request := httptest.NewRequest(method, path, reader)
	request.AddCookie(cookie)
	if body != "" {
		request.Header.Set("Content-Type", "application/json")
	}
	if csrfToken != "" {
		request.Header.Set("X-CSRF-Token", csrfToken)
	}
	return request
}
