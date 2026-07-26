package httpapi

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/agenttrace"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

type conversationHTTP struct {
	service          *conversation.Service
	proxy            *streamProxy
	v1Client         agent.Client
	logger           *slog.Logger
	maxRequestBytes  int64
	protocolMode     string
	runDeadline      time.Duration
	cancelTimeout    time.Duration
	reconcileTimeout time.Duration
}

type createConversationRequest struct {
	AgentName string `json:"agent_name"`
}

type updateConversationRequest struct {
	Title string `json:"title"`
}

type streamConversationRequest struct {
	Content         string `json:"content"`
	ClientMessageID string `json:"client_message_id"`
	AgentName       string `json:"agent_name"`
}

type upstreamChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type upstreamConversationRequest struct {
	Query       string                `json:"query"`
	AgentName   string                `json:"agent_name,omitempty"`
	ChatHistory []upstreamChatMessage `json:"chat_history,omitempty"`
}

func newConversationHTTP(
	service *conversation.Service,
	proxy *streamProxy,
	v1Client agent.Client,
	logger *slog.Logger,
	maxRequestBytes int64,
	protocolMode string,
	runDeadline time.Duration,
	cancelTimeout time.Duration,
	reconcileTimeout time.Duration,
) *conversationHTTP {
	return &conversationHTTP{
		service:          service,
		proxy:            proxy,
		v1Client:         v1Client,
		logger:           logger,
		maxRequestBytes:  maxRequestBytes,
		protocolMode:     protocolMode,
		runDeadline:      runDeadline,
		cancelTimeout:    cancelTimeout,
		reconcileTimeout: reconcileTimeout,
	}
}

func (h *conversationHTTP) create(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input createConversationRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	item, err := h.service.Create(r.Context(), session.User.ID, input.AgentName)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, item)
}

func (h *conversationHTTP) list(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	var before *time.Time
	if raw := strings.TrimSpace(r.URL.Query().Get("before")); raw != "" {
		value, err := time.Parse(time.RFC3339Nano, raw)
		if err != nil {
			writeJSONError(w, http.StatusBadRequest, "invalid_cursor")
			return
		}
		before = &value
	}
	items, err := h.service.List(
		r.Context(),
		session.User.ID,
		limit,
		r.URL.Query().Get("q"),
		before,
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	var nextBefore *time.Time
	if len(items) == limit {
		last := items[len(items)-1]
		if last.LastMessageAt != nil {
			value := *last.LastMessageAt
			nextBefore = &value
		} else {
			value := last.CreatedAt
			nextBefore = &value
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_before": nextBefore,
	})
}

func (h *conversationHTTP) get(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	item, err := h.service.Get(
		r.Context(),
		session.User.ID,
		r.PathValue("conversationID"),
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (h *conversationHTTP) rename(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input updateConversationRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	item, err := h.service.Rename(
		r.Context(),
		session.User.ID,
		r.PathValue("conversationID"),
		input.Title,
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (h *conversationHTTP) delete(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	err := h.service.Delete(
		r.Context(),
		session.User.ID,
		r.PathValue("conversationID"),
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *conversationHTTP) messages(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	var before *int64
	if raw := strings.TrimSpace(r.URL.Query().Get("before")); raw != "" {
		value, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			writeJSONError(w, http.StatusBadRequest, "invalid_cursor")
			return
		}
		before = &value
	}
	items, err := h.service.Messages(
		r.Context(),
		session.User.ID,
		r.PathValue("conversationID"),
		limit,
		before,
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	var nextBefore *int64
	if len(items) == limit {
		value := items[0].SequenceID
		nextBefore = &value
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_before": nextBefore,
	})
}

func (h *conversationHTTP) runs(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	effectiveLimit := limit
	if effectiveLimit <= 0 {
		effectiveLimit = 30
	}
	if effectiveLimit > 100 {
		effectiveLimit = 100
	}
	var before *time.Time
	if raw := strings.TrimSpace(r.URL.Query().Get("before")); raw != "" {
		value, err := time.Parse(time.RFC3339Nano, raw)
		if err != nil {
			writeJSONError(w, http.StatusBadRequest, "invalid_cursor")
			return
		}
		before = &value
	}
	items, err := h.service.ListRuns(
		r.Context(),
		session.User.ID,
		r.URL.Query().Get("status"),
		effectiveLimit,
		before,
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	var nextBefore *time.Time
	if len(items) == effectiveLimit {
		value := items[len(items)-1].StartedAt
		nextBefore = &value
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":       items,
		"next_before": nextBefore,
	})
}

func (h *conversationHTTP) runDetail(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	item, err := h.service.RunDetail(
		r.Context(),
		session.User.ID,
		r.PathValue("runID"),
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (h *conversationHTTP) stream(w http.ResponseWriter, r *http.Request) {
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	var input streamConversationRequest
	if err := decodeJSONBody(r, &input, h.maxRequestBytes); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_json")
		return
	}
	if h.protocolMode == "v1" {
		h.streamV1(w, r, session.User.ID, input)
		return
	}

	requestID := r.Header.Get(requestIDHeader)
	generation, err := h.service.Start(r.Context(), conversation.StartGenerationParams{
		UserID:          session.User.ID,
		ConversationID:  r.PathValue("conversationID"),
		ClientMessageID: input.ClientMessageID,
		RequestID:       requestID,
		Content:         input.Content,
		AgentName:       input.AgentName,
	})
	if err != nil {
		h.writeError(w, err)
		return
	}

	history, err := h.service.History(
		r.Context(),
		session.User.ID,
		generation.Conversation.ID,
	)
	if err != nil {
		h.finishDetached(session.User.ID, generation, "", "failed", "history_load_failed", err.Error(), nil)
		h.writeError(w, err)
		return
	}
	upstreamHistory := make([]upstreamChatMessage, 0, len(history))
	for _, message := range history {
		if message.ID == generation.UserMessage.ID {
			continue
		}
		upstreamHistory = append(upstreamHistory, upstreamChatMessage{
			Role:    message.Role,
			Content: message.Content,
		})
	}
	upstreamPayload, err := json.Marshal(upstreamConversationRequest{
		Query:       generation.UserMessage.Content,
		AgentName:   generation.Run.AgentName,
		ChatHistory: upstreamHistory,
	})
	if err != nil {
		h.finishDetached(session.User.ID, generation, "", "failed", "request_encode_failed", err.Error(), nil)
		writeJSONError(w, http.StatusInternalServerError, "request_encode_failed")
		return
	}

	upstreamRequest, err := http.NewRequestWithContext(
		r.Context(),
		http.MethodPost,
		h.proxy.upstreamURL,
		bytes.NewReader(upstreamPayload),
	)
	if err != nil {
		h.finishDetached(session.User.ID, generation, "", "failed", "upstream_request_failed", err.Error(), nil)
		writeJSONError(w, http.StatusInternalServerError, "cannot_create_upstream_request")
		return
	}
	copyRequestHeaders(upstreamRequest.Header, r.Header)
	signInternalRequest(
		upstreamRequest.Header,
		h.proxy.internalSecret,
		session.User.ID,
		requestID,
		upstreamPayload,
		time.Now().UTC(),
	)

	response, err := h.proxy.client.Do(upstreamRequest)
	if err != nil {
		status := "failed"
		code := "python_upstream_unavailable"
		if r.Context().Err() != nil {
			status = "stopped"
			code = "client_cancelled"
		}
		h.finishDetached(session.User.ID, generation, "", status, code, err.Error(), nil)
		if r.Context().Err() == nil {
			writeJSONError(w, http.StatusBadGateway, "python_upstream_unavailable")
		}
		return
	}
	defer response.Body.Close()

	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		detail, _ := io.ReadAll(io.LimitReader(response.Body, 1<<20))
		h.finishDetached(
			session.User.ID,
			generation,
			"",
			"failed",
			"python_upstream_error",
			string(detail),
			nil,
		)
		writeJSONError(w, http.StatusBadGateway, "python_upstream_error")
		return
	}

	copyResponseHeaders(w.Header(), response.Header)
	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	flusher, ok := w.(http.Flusher)
	if !ok {
		h.finishDetached(session.User.ID, generation, "", "failed", "streaming_not_supported", "", nil)
		return
	}
	writeSSEJSON(w, map[string]any{
		"type":                 "meta",
		"conversation_id":      generation.Conversation.ID,
		"user_message_id":      generation.UserMessage.ID,
		"assistant_message_id": generation.Assistant.ID,
		"run_id":               generation.Run.ID,
		"title":                generation.Conversation.Title,
	})
	flusher.Flush()

	var (
		answer             strings.Builder
		firstTokenAt       *time.Time
		lastCheckpoint     = time.Now()
		checkpointLength   int
		finished           bool
		finishStatus       = "stopped"
		finishCode         = "stream_interrupted"
		finishDetail       string
		reader             = bufio.NewReader(response.Body)
		checkpointInterval = 2 * time.Second
	)
	defer func() {
		if !finished {
			h.finishDetached(
				session.User.ID,
				generation,
				answer.String(),
				finishStatus,
				finishCode,
				finishDetail,
				firstTokenAt,
			)
		}
	}()

	for {
		line, readErr := reader.ReadString('\n')
		if len(line) > 0 {
			event := parseSSEDataLine(line)
			if event.Type == "delta" {
				if !event.IsThinking && event.Data != "" {
					answer.WriteString(event.Data)
					if firstTokenAt == nil {
						now := time.Now().UTC()
						firstTokenAt = &now
					}
				}
			}

			if event.Type == "done" {
				if strings.TrimSpace(answer.String()) == "" {
					if err := h.finishGeneration(
						session.User.ID,
						generation,
						"",
						"failed",
						"empty_agent_response",
						"Python Agent completed without an answer",
						firstTokenAt,
					); err == nil {
						finished = true
					}
					writeSSEJSON(w, map[string]any{
						"type":    "error",
						"message": "Agent 未返回有效回答，请重试",
					})
					flusher.Flush()
					return
				}
				if err := h.finishGeneration(
					session.User.ID,
					generation,
					answer.String(),
					"completed",
					"",
					"",
					firstTokenAt,
				); err != nil {
					finishStatus = "failed"
					finishCode = "persistence_failed"
					finishDetail = err.Error()
					return
				}
				finished = true
				writeSSEJSON(w, map[string]any{
					"type":       "done",
					"message_id": generation.Assistant.ID,
					"status":     "completed",
				})
				flusher.Flush()
				return
			}

			if event.Type == "error" {
				finishStatus = "failed"
				finishCode = "agent_error"
				finishDetail = event.Message
				if err := h.finishGeneration(
					session.User.ID,
					generation,
					answer.String(),
					finishStatus,
					finishCode,
					finishDetail,
					firstTokenAt,
				); err == nil {
					finished = true
				}
			}

			if event.Type != "done" {
				if _, err := io.WriteString(w, line); err != nil {
					finishStatus = "stopped"
					finishCode = "client_cancelled"
					finishDetail = err.Error()
					return
				}
				flusher.Flush()
			}

			if answer.Len()-checkpointLength >= 2048 ||
				time.Since(lastCheckpoint) >= checkpointInterval {
				if err := h.service.Checkpoint(
					r.Context(),
					session.User.ID,
					generation.Assistant.ID,
					answer.String(),
				); err == nil {
					checkpointLength = answer.Len()
					lastCheckpoint = time.Now()
				}
			}
		}
		if readErr != nil {
			if !errors.Is(readErr, io.EOF) && !errors.Is(readErr, context.Canceled) {
				finishStatus = "failed"
				finishCode = "python_stream_closed"
				finishDetail = readErr.Error()
			} else if r.Context().Err() != nil {
				finishStatus = "stopped"
				finishCode = "client_cancelled"
			}
			return
		}
	}
}

func (h *conversationHTTP) streamV1(
	w http.ResponseWriter,
	r *http.Request,
	userID string,
	input streamConversationRequest,
) {
	requestID := r.Header.Get(requestIDHeader)
	generation, err := h.service.Start(r.Context(), conversation.StartGenerationParams{
		UserID:          userID,
		ConversationID:  r.PathValue("conversationID"),
		ClientMessageID: input.ClientMessageID,
		RequestID:       requestID,
		Content:         input.Content,
		AgentName:       input.AgentName,
		ProtocolVersion: agent.ProtocolVersion,
	})
	if err != nil {
		h.writeError(w, err)
		return
	}

	history, err := h.service.History(
		r.Context(),
		userID,
		generation.Conversation.ID,
	)
	if err != nil {
		h.finishDetached(
			userID,
			generation,
			"",
			"failed",
			"history_load_failed",
			err.Error(),
			nil,
		)
		h.writeError(w, err)
		return
	}
	messages := make([]agent.Message, 0, len(history))
	for _, message := range history {
		if message.ID == generation.UserMessage.ID {
			continue
		}
		messages = append(messages, agent.Message{
			Role:    message.Role,
			Content: message.Content,
		})
	}
	runRequest := agent.RunRequest{
		ProtocolVersion: agent.ProtocolVersion,
		ExecutionID:     generation.Run.ExecutionID,
		RunID:           generation.Run.ID,
		RequestID:       generation.Run.RequestID,
		IdempotencyKey:  generation.Run.ExecutionID,
		ConversationID:  generation.Conversation.ID,
		AgentName:       generation.Run.AgentName,
		Query:           generation.UserMessage.Content,
		Messages:        messages,
		DeadlineMS:      h.runDeadline.Milliseconds(),
		UserID:          userID,
	}
	stream, err := h.v1Client.Start(r.Context(), runRequest)
	if err != nil {
		h.finishDetached(
			userID,
			generation,
			"",
			"failed",
			"python_upstream_unavailable",
			err.Error(),
			nil,
		)
		writeJSONError(w, http.StatusBadGateway, "python_upstream_unavailable")
		return
	}
	defer stream.Close()

	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("X-Accel-Buffering", "no")
	w.WriteHeader(http.StatusOK)
	flusher, ok := w.(http.Flusher)
	if !ok {
		h.finishDetached(
			userID,
			generation,
			"",
			"failed",
			"streaming_not_supported",
			"",
			nil,
		)
		return
	}
	writeSSEJSON(w, map[string]any{
		"type":                 "meta",
		"conversation_id":      generation.Conversation.ID,
		"user_message_id":      generation.UserMessage.ID,
		"assistant_message_id": generation.Assistant.ID,
		"run_id":               generation.Run.ID,
		"execution_id":         generation.Run.ExecutionID,
		"title":                generation.Conversation.Title,
	})
	flusher.Flush()

	var (
		answer             strings.Builder
		firstTokenAt       *time.Time
		lastCheckpoint     = time.Now()
		checkpointLength   int
		lastSequence       int64
		finished           bool
		terminalStatus     = "failed"
		terminalCode       = "python_stream_closed"
		terminalDetail     string
		checkpointInterval = 2 * time.Second
	)
	defer func() {
		if finished {
			return
		}
		if r.Context().Err() != nil {
			terminalStatus = string(agent.StatusCancelled)
			terminalCode = "client_cancelled"
		}
		h.cancelV1Run(
			r,
			userID,
			generation,
			answer.String(),
			firstTokenAt,
			terminalStatus,
			terminalCode,
			terminalDetail,
		)
	}()

	for {
		event, nextErr := stream.Next()
		if nextErr != nil && !errors.Is(nextErr, agent.ErrSequenceGap) {
			if !agent.IsStreamDone(nextErr) {
				terminalDetail = nextErr.Error()
			}
			if r.Context().Err() != nil {
				terminalStatus = string(agent.StatusCancelled)
				terminalCode = "client_cancelled"
			}
			return
		}
		if errors.Is(nextErr, agent.ErrSequenceGap) {
			expected := lastSequence + 1
			_ = h.service.MarkSequenceGap(
				context.WithoutCancel(r.Context()),
				userID,
				generation.Run.ID,
				expected,
				event.Sequence,
			)
			reconcileCtx, cancel := context.WithTimeout(
				context.WithoutCancel(r.Context()),
				h.reconcileTimeout,
			)
			_, reconcileErr := h.v1Client.Get(
				reconcileCtx,
				userID,
				requestID,
				generation.Run.ExecutionID,
			)
			cancel()
			if reconcileErr != nil {
				h.logger.Warn(
					"agent_sequence_reconcile_failed",
					"error", reconcileErr,
					"run_id", generation.Run.ID,
					"expected", expected,
					"received", event.Sequence,
				)
			}
		}
		if event.Sequence <= lastSequence {
			continue
		}
		lastSequence = event.Sequence
		if agenttrace.ShouldPersist(event.Type) {
			storedEvent := event
			storedEvent.Data = agenttrace.Sanitize(event.Data)
			if _, err := h.service.RecordEvent(
				context.WithoutCancel(r.Context()),
				userID,
				generation.Run.ID,
				storedEvent,
			); err != nil {
				terminalDetail = err.Error()
				terminalCode = "event_persistence_failed"
				return
			}
		}

		var data map[string]any
		_ = json.Unmarshal(event.Data, &data)
		switch event.Type {
		case "progress":
			message, _ := data["message"].(string)
			if message != "" {
				writeSSEJSON(w, map[string]any{
					"type":             "delta",
					"data":             message + "\n",
					"isThinking":       true,
					"thinkingFinished": false,
				})
				flusher.Flush()
			}
		case "tool.completed":
			name, _ := data["name"].(string)
			if name != "" {
				writeSSEJSON(w, map[string]any{
					"type":             "delta",
					"data":             "已完成工具：" + name + "\n",
					"isThinking":       true,
					"thinkingFinished": false,
				})
				flusher.Flush()
			}
		case "answer.delta":
			text, _ := data["text"].(string)
			if text != "" {
				answer.WriteString(text)
				if firstTokenAt == nil {
					now := time.Now().UTC()
					firstTokenAt = &now
				}
				writeSSEJSON(w, map[string]any{
					"type":             "delta",
					"data":             text,
					"isThinking":       false,
					"thinkingFinished": true,
				})
				flusher.Flush()
			}
		case "run.completed":
			if strings.TrimSpace(answer.String()) == "" {
				terminalStatus = "failed"
				terminalCode = "empty_agent_response"
				terminalDetail = "Python Agent completed without an answer"
				writeSSEJSON(w, map[string]any{
					"type":    "error",
					"message": "Agent 未返回有效回答，请重试",
				})
				flusher.Flush()
				return
			}
			if err := h.finishGeneration(
				userID,
				generation,
				answer.String(),
				"completed",
				"",
				"",
				firstTokenAt,
			); err != nil {
				terminalDetail = err.Error()
				terminalCode = "persistence_failed"
				return
			}
			finished = true
			writeSSEJSON(w, map[string]any{
				"type":       "done",
				"message_id": generation.Assistant.ID,
				"status":     "completed",
			})
			flusher.Flush()
			return
		case "run.cancelled":
			_ = h.finishGeneration(
				userID,
				generation,
				answer.String(),
				string(agent.StatusCancelled),
				"generation_cancelled",
				"",
				firstTokenAt,
			)
			finished = true
			writeSSEJSON(w, map[string]any{
				"type":       "done",
				"message_id": generation.Assistant.ID,
				"status":     "stopped",
			})
			flusher.Flush()
			return
		case "run.failed", "run.timed_out":
			code, _ := data["code"].(string)
			message, _ := data["message"].(string)
			status := "failed"
			if event.Type == "run.timed_out" {
				status = string(agent.StatusTimedOut)
			}
			_ = h.finishGeneration(
				userID,
				generation,
				answer.String(),
				status,
				code,
				message,
				firstTokenAt,
			)
			finished = true
			writeSSEJSON(w, map[string]any{
				"type":    "error",
				"message": "Agent 执行失败，请稍后重试",
			})
			flusher.Flush()
			return
		}

		if answer.Len()-checkpointLength >= 2048 ||
			time.Since(lastCheckpoint) >= checkpointInterval {
			if err := h.service.Checkpoint(
				r.Context(),
				userID,
				generation.Assistant.ID,
				answer.String(),
			); err == nil {
				checkpointLength = answer.Len()
				lastCheckpoint = time.Now()
			}
		}
	}
}

func (h *conversationHTTP) cancelV1Run(
	r *http.Request,
	userID string,
	generation conversation.Generation,
	content string,
	firstTokenAt *time.Time,
	fallbackStatus string,
	fallbackCode string,
	fallbackDetail string,
) {
	cancelCtx, cancel := context.WithTimeout(
		context.WithoutCancel(r.Context()),
		h.cancelTimeout,
	)
	defer cancel()
	_ = h.service.RequestCancellation(
		cancelCtx,
		userID,
		generation.Run.ID,
	)
	snapshot, err := h.v1Client.Cancel(
		cancelCtx,
		userID,
		generation.Run.RequestID,
		generation.Run.ExecutionID,
	)
	if err == nil {
		ticker := time.NewTicker(50 * time.Millisecond)
		defer ticker.Stop()
		for !snapshot.Status.Terminal() {
			select {
			case <-cancelCtx.Done():
				err = cancelCtx.Err()
			case <-ticker.C:
				snapshot, err = h.v1Client.Get(
					cancelCtx,
					userID,
					generation.Run.RequestID,
					generation.Run.ExecutionID,
				)
			}
			if err != nil {
				break
			}
		}
	}
	status := fallbackStatus
	code := fallbackCode
	detail := fallbackDetail
	if err == nil && snapshot.Status.Terminal() {
		status = string(snapshot.Status)
		if status == string(agent.StatusCompleted) && strings.TrimSpace(content) == "" {
			status = "failed"
			code = "empty_agent_response"
		}
	}
	h.finishDetached(
		userID,
		generation,
		content,
		status,
		code,
		detail,
		firstTokenAt,
	)
}

type parsedSSEEvent struct {
	Type       string `json:"type"`
	Data       string `json:"data"`
	Message    string `json:"message"`
	IsThinking bool   `json:"isThinking"`
}

func parseSSEDataLine(line string) parsedSSEEvent {
	trimmed := strings.TrimSpace(line)
	if !strings.HasPrefix(trimmed, "data:") {
		return parsedSSEEvent{}
	}
	payload := strings.TrimSpace(strings.TrimPrefix(trimmed, "data:"))
	var event parsedSSEEvent
	_ = json.Unmarshal([]byte(payload), &event)
	return event
}

func writeSSEJSON(w io.Writer, payload any) {
	data, _ := json.Marshal(payload)
	_, _ = fmt.Fprintf(w, "event: message\ndata: %s\n\n", data)
}

func (h *conversationHTTP) finishGeneration(
	userID string,
	generation conversation.Generation,
	content string,
	status string,
	code string,
	detail string,
	firstTokenAt *time.Time,
) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	return h.service.Finish(ctx, conversation.FinishGenerationParams{
		UserID:              userID,
		RunID:               generation.Run.ID,
		AssistantMessageID:  generation.Assistant.ID,
		Content:             content,
		Status:              status,
		ErrorCode:           code,
		ErrorDetail:         detail,
		FirstTokenAt:        firstTokenAt,
		GenerationCompleted: time.Now().UTC(),
	})
}

func (h *conversationHTTP) finishDetached(
	userID string,
	generation conversation.Generation,
	content string,
	status string,
	code string,
	detail string,
	firstTokenAt *time.Time,
) {
	if err := h.finishGeneration(
		userID,
		generation,
		content,
		status,
		code,
		detail,
		firstTokenAt,
	); err != nil {
		h.logger.Error(
			"persist_generation_terminal_state",
			"error", err,
			"run_id", generation.Run.ID,
		)
	}
}

func (h *conversationHTTP) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, conversation.ErrNotFound):
		writeJSONError(w, http.StatusNotFound, "conversation_not_found")
	case errors.Is(err, conversation.ErrInvalidInput):
		writeJSONError(w, http.StatusBadRequest, "invalid_conversation_input")
	case errors.Is(err, conversation.ErrGenerationActive):
		writeJSONError(w, http.StatusConflict, "conversation_busy")
	case errors.Is(err, conversation.ErrDuplicateMessage):
		writeJSONError(w, http.StatusConflict, "duplicate_message")
	default:
		h.logger.Error("conversation_api_error", "error", err)
		writeJSONError(w, http.StatusInternalServerError, "internal_error")
	}
}
