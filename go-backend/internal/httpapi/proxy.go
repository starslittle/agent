package httpapi

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"mime"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type streamProxy struct {
	upstreamURL    string
	maxRequestSize int64
	client         *http.Client
	logger         *slog.Logger
	internalSecret []byte
}

type queryRequest struct {
	Query string `json:"query"`
}

func newStreamProxy(
	pythonBaseURL string,
	maxRequestSize int64,
	headerTimeout time.Duration,
	internalSecret string,
	logger *slog.Logger,
) (*streamProxy, error) {
	baseURL, err := url.Parse(pythonBaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse Python base URL: %w", err)
	}
	upstreamURL := baseURL.ResolveReference(&url.URL{Path: "/query_stream"}).String()
	transport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		DialContext:           (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		ForceAttemptHTTP2:     false,
		DisableCompression:    true,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   20,
		IdleConnTimeout:       90 * time.Second,
		ResponseHeaderTimeout: headerTimeout,
	}
	return &streamProxy{
		upstreamURL:    upstreamURL,
		maxRequestSize: maxRequestSize,
		client:         &http.Client{Transport: transport},
		logger:         logger,
		internalSecret: []byte(internalSecret),
	}, nil
}

func (p *streamProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", http.MethodPost)
		writeJSONError(w, http.StatusMethodNotAllowed, "method_not_allowed")
		return
	}

	mediaType, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		writeJSONError(w, http.StatusUnsupportedMediaType, "content_type_must_be_application_json")
		return
	}

	body, err := readRequestBody(r.Body, p.maxRequestSize)
	if err != nil {
		if errors.Is(err, errRequestTooLarge) {
			writeJSONError(w, http.StatusRequestEntityTooLarge, "request_too_large")
			return
		}
		writeJSONError(w, http.StatusBadRequest, "invalid_request_body")
		return
	}

	var payload queryRequest
	if err := json.Unmarshal(body, &payload); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	if strings.TrimSpace(payload.Query) == "" {
		writeJSONError(w, http.StatusBadRequest, "query_is_required")
		return
	}

	upstreamRequest, err := http.NewRequestWithContext(
		r.Context(),
		http.MethodPost,
		p.upstreamURL,
		bytes.NewReader(body),
	)
	if err != nil {
		writeJSONError(w, http.StatusInternalServerError, "cannot_create_upstream_request")
		return
	}
	copyRequestHeaders(upstreamRequest.Header, r.Header)
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	signInternalRequest(
		upstreamRequest.Header,
		p.internalSecret,
		session.User.ID,
		r.Header.Get(requestIDHeader),
		body,
		time.Now().UTC(),
	)

	response, err := p.client.Do(upstreamRequest)
	if err != nil {
		if r.Context().Err() != nil {
			return
		}
		p.logger.Error(
			"python_upstream_error",
			"error", err,
			"request_id", r.Header.Get(requestIDHeader),
		)
		writeJSONError(w, http.StatusBadGateway, "python_upstream_unavailable")
		return
	}
	defer response.Body.Close()

	copyResponseHeaders(w.Header(), response.Header)
	w.WriteHeader(response.StatusCode)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		_, _ = io.Copy(w, io.LimitReader(response.Body, 1<<20))
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		p.logger.Error("streaming_not_supported")
		return
	}
	// Send the upstream SSE headers immediately. This gives the browser an
	// observable first response and lets disconnect cancellation propagate even
	// when Python has not emitted its first data frame yet.
	flusher.Flush()

	buffer := make([]byte, 32*1024)
	for {
		count, readErr := response.Body.Read(buffer)
		if count > 0 {
			if _, writeErr := w.Write(buffer[:count]); writeErr != nil {
				return
			}
			flusher.Flush()
		}
		if readErr != nil {
			if !errors.Is(readErr, io.EOF) && !errors.Is(readErr, context.Canceled) {
				p.logger.Warn(
					"python_stream_closed",
					"error", readErr,
					"request_id", r.Header.Get(requestIDHeader),
				)
			}
			return
		}
	}
}

var errRequestTooLarge = errors.New("request body is too large")

func readRequestBody(body io.ReadCloser, limit int64) ([]byte, error) {
	defer body.Close()
	reader := io.LimitReader(body, limit+1)
	content, err := io.ReadAll(reader)
	if err != nil {
		return nil, err
	}
	if int64(len(content)) > limit {
		return nil, errRequestTooLarge
	}
	return content, nil
}

func copyRequestHeaders(target, source http.Header) {
	for _, name := range []string{"Traceparent", "Tracestate"} {
		if value := source.Get(name); value != "" {
			target.Set(name, value)
		}
	}
	target.Set(requestIDHeader, source.Get(requestIDHeader))
	target.Set("Accept", "text/event-stream")
	target.Set("Content-Type", "application/json")
}

func signInternalRequest(
	headers http.Header,
	secret []byte,
	userID string,
	requestID string,
	body []byte,
	now time.Time,
) {
	timestamp := now.Format(time.RFC3339)
	bodyHash := sha256.Sum256(body)
	canonical := strings.Join([]string{
		userID,
		requestID,
		timestamp,
		hex.EncodeToString(bodyHash[:]),
	}, "\n")
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(canonical))
	headers.Set("X-Qidian-User-ID", userID)
	headers.Set("X-Qidian-Timestamp", timestamp)
	headers.Set("X-Qidian-Signature", hex.EncodeToString(mac.Sum(nil)))
}

func copyResponseHeaders(target, source http.Header) {
	for name, values := range source {
		if isHopByHopHeader(name) || strings.EqualFold(name, "Content-Length") {
			continue
		}
		switch http.CanonicalHeaderKey(name) {
		case "Set-Cookie", "Access-Control-Allow-Origin", "Access-Control-Allow-Credentials":
			continue
		}
		for _, value := range values {
			target.Add(name, value)
		}
	}
	target.Set("X-Accel-Buffering", "no")
}

func isHopByHopHeader(name string) bool {
	switch http.CanonicalHeaderKey(name) {
	case "Connection", "Keep-Alive", "Proxy-Authenticate", "Proxy-Authorization",
		"Te", "Trailer", "Transfer-Encoding", "Upgrade":
		return true
	default:
		return false
	}
}
