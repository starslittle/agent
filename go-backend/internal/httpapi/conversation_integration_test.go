package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

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
