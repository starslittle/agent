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
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/config"
)

func TestQueryStreamPreservesSSEBytesAndRequestID(t *testing.T) {
	var contract struct {
		Request  json.RawMessage `json:"request"`
		Response string          `json:"response"`
	}
	fixture, err := os.ReadFile(filepath.Join("testdata", "query_stream_contract.json"))
	if err != nil {
		t.Fatalf("read contract fixture: %v", err)
	}
	if err := json.Unmarshal(fixture, &contract); err != nil {
		t.Fatalf("decode contract fixture: %v", err)
	}
	expected := contract.Response

	receivedRequestID := make(chan string, 1)
	receivedBody := make(chan []byte, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedRequestID <- r.Header.Get(requestIDHeader)
		body, _ := io.ReadAll(r.Body)
		receivedBody <- body
		if r.URL.Path != "/query_stream" {
			t.Errorf("upstream path = %q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		_, _ = io.WriteString(w, expected[:len(expected)/2])
		w.(http.Flusher).Flush()
		_, _ = io.WriteString(w, expected[len(expected)/2:])
		w.(http.Flusher).Flush()
	}))
	defer upstream.Close()

	gateway := newTestGateway(t, upstream.URL)
	request := httptest.NewRequest(
		http.MethodPost,
		"/query_stream",
		bytes.NewReader(contract.Request),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(requestIDHeader, "request-from-client")
	response := httptest.NewRecorder()

	gateway.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if response.Body.String() != expected {
		t.Fatalf("SSE body changed:\n%q\nwant:\n%q", response.Body.String(), expected)
	}
	if response.Header().Get(requestIDHeader) != "request-from-client" {
		t.Fatalf("response request ID = %q", response.Header().Get(requestIDHeader))
	}
	if requestID := <-receivedRequestID; requestID != "request-from-client" {
		t.Fatalf("upstream request ID = %q", requestID)
	}
	var upstreamPayload map[string]any
	if err := json.Unmarshal(<-receivedBody, &upstreamPayload); err != nil {
		t.Fatalf("upstream request is not JSON: %v", err)
	}
	if upstreamPayload["agent_name"] != "default_llm_agent" {
		t.Fatalf("agent_name was changed: %#v", upstreamPayload["agent_name"])
	}
}

func TestQueryStreamValidatesRequest(t *testing.T) {
	gateway := newTestGateway(t, "http://127.0.0.1:1")
	request := httptest.NewRequest(
		http.MethodPost,
		"/query_stream",
		strings.NewReader(`{"query":"   "}`),
	)
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()

	gateway.ServeHTTP(response, request)

	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusBadRequest)
	}
}

func TestHealthAndReadiness(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/healthz" {
			http.NotFound(w, r)
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}))
	defer upstream.Close()
	gateway := newTestGateway(t, upstream.URL)

	for _, path := range []string{"/healthz", "/readyz"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		gateway.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s status = %d", path, response.Code)
		}
		var payload map[string]any
		if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
			t.Fatalf("%s invalid JSON: %v", path, err)
		}
	}
}

func TestStaticFilesAndSPAFallback(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	}))
	defer upstream.Close()

	staticDir := t.TempDir()
	if err := os.WriteFile(
		filepath.Join(staticDir, "index.html"),
		[]byte("<main>qidian app</main>"),
		0o600,
	); err != nil {
		t.Fatalf("write index fixture: %v", err)
	}
	if err := os.WriteFile(
		filepath.Join(staticDir, "asset.txt"),
		[]byte("static asset"),
		0o600,
	); err != nil {
		t.Fatalf("write asset fixture: %v", err)
	}

	cfg := config.Config{
		HTTPAddr:              ":0",
		PythonBaseURL:         upstream.URL,
		StaticDir:             staticDir,
		MaxRequestBytes:       1 << 20,
		UpstreamHeaderTimeout: 2 * time.Second,
		ShutdownTimeout:       time.Second,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server, err := New(cfg, logger)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	for path, expected := range map[string]string{
		"/asset.txt":  "static asset",
		"/chat/12345": "<main>qidian app</main>",
	} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		response := httptest.NewRecorder()
		server.Handler().ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("%s status = %d", path, response.Code)
		}
		if strings.TrimSpace(response.Body.String()) != expected {
			t.Fatalf("%s body = %q", path, response.Body.String())
		}
	}
}

func TestClientCancellationPropagatesToPython(t *testing.T) {
	started := make(chan struct{})
	cancelled := make(chan struct{})
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		w.(http.Flusher).Flush()
		close(started)
		<-r.Context().Done()
		close(cancelled)
	}))
	defer upstream.Close()

	gateway := httptest.NewServer(newTestGateway(t, upstream.URL))
	defer gateway.Close()
	ctx, cancel := context.WithCancel(context.Background())
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		gateway.URL+"/query_stream",
		strings.NewReader(`{"query":"等待"}`),
	)
	if err != nil {
		t.Fatalf("NewRequestWithContext() error = %v", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("gateway request error = %v", err)
	}

	select {
	case <-started:
	case <-time.After(2 * time.Second):
		t.Fatal("upstream request did not start")
	}
	cancel()
	_ = response.Body.Close()

	select {
	case <-cancelled:
	case <-time.After(2 * time.Second):
		t.Fatal("upstream context was not cancelled")
	}
}

func newTestGateway(t *testing.T, pythonBaseURL string) http.Handler {
	t.Helper()
	cfg := config.Config{
		HTTPAddr:              ":0",
		PythonBaseURL:         pythonBaseURL,
		MaxRequestBytes:       1 << 20,
		UpstreamHeaderTimeout: 2 * time.Second,
		ShutdownTimeout:       time.Second,
	}
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	server, err := New(cfg, logger)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	return server.Handler()
}
