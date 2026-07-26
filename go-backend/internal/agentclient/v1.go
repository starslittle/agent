package agentclient

import (
	"bufio"
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

type V1Client struct {
	baseURL *url.URL
	client  *http.Client
	secret  []byte
}

func NewV1(
	baseURL string,
	client *http.Client,
	secret string,
) (*V1Client, error) {
	parsed, err := url.Parse(strings.TrimRight(baseURL, "/"))
	if err != nil {
		return nil, fmt.Errorf("parse Python Agent URL: %w", err)
	}
	return &V1Client{
		baseURL: parsed,
		client:  client,
		secret:  []byte(secret),
	}, nil
}

func (c *V1Client) Start(
	ctx context.Context,
	run agent.RunRequest,
) (agent.EventStream, error) {
	return c.start(ctx, run, 0)
}

func (c *V1Client) Resume(
	ctx context.Context,
	run agent.RunRequest,
	startingAfter int64,
) (agent.EventStream, error) {
	if startingAfter < 0 {
		return nil, errors.New("starting_after cannot be negative")
	}
	return c.start(ctx, run, startingAfter)
}

func (c *V1Client) start(
	ctx context.Context,
	run agent.RunRequest,
	startingAfter int64,
) (agent.EventStream, error) {
	if err := run.Validate(); err != nil {
		return nil, err
	}
	body, err := json.Marshal(run)
	if err != nil {
		return nil, err
	}
	path := "/internal/v1/agent-runs:stream"
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.resolve(path),
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, err
	}
	if startingAfter > 0 {
		query := request.URL.Query()
		query.Set("starting_after", strconv.FormatInt(startingAfter, 10))
		request.URL.RawQuery = query.Encode()
	}
	request.Header.Set("Accept", "text/event-stream")
	request.Header.Set("Content-Type", "application/json")
	c.sign(request, run.UserID, run.RequestID, run.ExecutionID, body)
	response, err := c.client.Do(request)
	if err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		defer response.Body.Close()
		detail, _ := io.ReadAll(io.LimitReader(response.Body, 1<<20))
		return nil, fmt.Errorf(
			"Python Agent start failed (%d): %s",
			response.StatusCode,
			strings.TrimSpace(string(detail)),
		)
	}
	return &v1EventStream{
		body:        response.Body,
		reader:      bufio.NewReader(response.Body),
		executionID: run.ExecutionID,
		last:        startingAfter,
	}, nil
}

func (c *V1Client) Get(
	ctx context.Context,
	userID string,
	requestID string,
	executionID string,
) (agent.Snapshot, error) {
	return c.snapshotRequest(
		ctx,
		http.MethodGet,
		userID,
		requestID,
		executionID,
	)
}

func (c *V1Client) Cancel(
	ctx context.Context,
	userID string,
	requestID string,
	executionID string,
) (agent.Snapshot, error) {
	return c.snapshotRequest(
		ctx,
		http.MethodDelete,
		userID,
		requestID,
		executionID,
	)
}

func (c *V1Client) snapshotRequest(
	ctx context.Context,
	method string,
	userID string,
	requestID string,
	executionID string,
) (agent.Snapshot, error) {
	path := "/internal/v1/agent-runs/" + url.PathEscape(executionID)
	request, err := http.NewRequestWithContext(ctx, method, c.resolve(path), nil)
	if err != nil {
		return agent.Snapshot{}, err
	}
	request.Header.Set("Accept", "application/json")
	c.sign(request, userID, requestID, executionID, nil)
	response, err := c.client.Do(request)
	if err != nil {
		return agent.Snapshot{}, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		detail, _ := io.ReadAll(io.LimitReader(response.Body, 1<<20))
		return agent.Snapshot{}, fmt.Errorf(
			"Python Agent %s failed (%d): %s",
			method,
			response.StatusCode,
			strings.TrimSpace(string(detail)),
		)
	}
	var snapshot agent.Snapshot
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&snapshot); err != nil {
		return agent.Snapshot{}, err
	}
	return snapshot, nil
}

func (c *V1Client) resolve(path string) string {
	return c.baseURL.ResolveReference(&url.URL{Path: path}).String()
}

func (c *V1Client) sign(
	request *http.Request,
	userID string,
	requestID string,
	executionID string,
	body []byte,
) {
	timestamp := time.Now().UTC().Format(time.RFC3339Nano)
	nonceBytes := make([]byte, 16)
	if _, err := rand.Read(nonceBytes); err != nil {
		panic("crypto/rand unavailable")
	}
	nonce := hex.EncodeToString(nonceBytes)
	bodyHash := sha256.Sum256(body)
	canonical := strings.Join([]string{
		strconv.Itoa(agent.ProtocolVersion),
		request.Method,
		request.URL.EscapedPath(),
		userID,
		executionID,
		requestID,
		timestamp,
		nonce,
		hex.EncodeToString(bodyHash[:]),
	}, "\n")
	mac := hmac.New(sha256.New, c.secret)
	_, _ = mac.Write([]byte(canonical))
	request.Header.Set("X-Qidian-Signature-Version", "v1")
	request.Header.Set("X-Qidian-User-ID", userID)
	request.Header.Set("X-Qidian-Execution-ID", executionID)
	request.Header.Set("X-Request-ID", requestID)
	request.Header.Set("X-Qidian-Timestamp", timestamp)
	request.Header.Set("X-Qidian-Nonce", nonce)
	request.Header.Set("X-Qidian-Signature", hex.EncodeToString(mac.Sum(nil)))
}

type v1EventStream struct {
	body        io.ReadCloser
	reader      *bufio.Reader
	executionID string
	last        int64
}

func (s *v1EventStream) Close() error {
	return s.body.Close()
}

func (s *v1EventStream) Next() (agent.Event, error) {
	for {
		frame, err := readSSEFrame(s.reader)
		if err != nil {
			return agent.Event{}, err
		}
		if len(frame.data) == 0 {
			continue
		}
		var event agent.Event
		if err := json.Unmarshal(frame.data, &event); err != nil {
			return agent.Event{}, fmt.Errorf("decode Agent event: %w", err)
		}
		if err := event.Validate(s.executionID); err != nil {
			return agent.Event{}, err
		}
		if frame.event != "" && frame.event != event.Type {
			return agent.Event{}, errors.New("SSE event type mismatch")
		}
		if frame.id != "" && frame.id != event.SSEID() {
			return agent.Event{}, errors.New("SSE event id mismatch")
		}
		if event.Sequence <= s.last {
			continue
		}
		if event.Sequence != s.last+1 {
			return event, agent.ErrSequenceGap
		}
		s.last = event.Sequence
		return event, nil
	}
}

type sseFrame struct {
	event string
	id    string
	data  []byte
}

func readSSEFrame(reader *bufio.Reader) (sseFrame, error) {
	var frame sseFrame
	var data []string
	for {
		line, err := reader.ReadString('\n')
		if err != nil && len(line) == 0 {
			return sseFrame{}, err
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			frame.data = []byte(strings.Join(data, "\n"))
			return frame, nil
		}
		if strings.HasPrefix(line, ":") {
			if err != nil {
				return sseFrame{}, err
			}
			continue
		}
		name, value, found := strings.Cut(line, ":")
		if found {
			value = strings.TrimPrefix(value, " ")
		}
		switch name {
		case "event":
			frame.event = value
		case "id":
			frame.id = value
		case "data":
			data = append(data, value)
		}
		if err != nil {
			return sseFrame{}, err
		}
	}
}
