package postgres

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/agenttrace"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func (s *Store) CreateConversation(
	ctx context.Context,
	id string,
	userID string,
	agentName string,
) (conversation.Conversation, error) {
	var item conversation.Conversation
	err := s.pool.QueryRow(ctx, `
		INSERT INTO app_core.conversations (id, user_id, agent_name)
		VALUES ($1, $2, $3)
		RETURNING
			id::text, user_id::text, title, agent_name, status,
			last_message_at, created_at, updated_at
	`, id, userID, agentName).Scan(
		&item.ID,
		&item.UserID,
		&item.Title,
		&item.AgentName,
		&item.Status,
		&item.LastMessageAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	return item, mapConversationError(err)
}

func (s *Store) ListConversations(
	ctx context.Context,
	params conversation.ListParams,
) ([]conversation.Conversation, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT
			c.id::text,
			c.user_id::text,
			c.title,
			c.agent_name,
			c.status,
			c.last_message_at,
			c.created_at,
			c.updated_at,
			COALESCE(last_message.content, '')
		FROM app_core.conversations c
		LEFT JOIN LATERAL (
			SELECT content
			FROM app_core.messages m
			WHERE m.conversation_id = c.id
				AND m.content <> ''
			ORDER BY m.sequence_id DESC
			LIMIT 1
		) last_message ON TRUE
		WHERE c.user_id = $1
			AND c.deleted_at IS NULL
			AND c.status <> 'deleted'
			AND ($2 = '' OR c.title ILIKE '%' || $2 || '%'
				OR COALESCE(last_message.content, '') ILIKE '%' || $2 || '%')
			AND ($3::timestamptz IS NULL
				OR COALESCE(c.last_message_at, c.created_at) < $3)
		ORDER BY COALESCE(c.last_message_at, c.created_at) DESC, c.id DESC
		LIMIT $4
	`, params.UserID, params.Query, params.Before, params.Limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]conversation.Conversation, 0, params.Limit)
	for rows.Next() {
		var item conversation.Conversation
		if err := rows.Scan(
			&item.ID,
			&item.UserID,
			&item.Title,
			&item.AgentName,
			&item.Status,
			&item.LastMessageAt,
			&item.CreatedAt,
			&item.UpdatedAt,
			&item.LastMessagePreview,
		); err != nil {
			return nil, err
		}
		item.LastMessagePreview = truncateRunes(
			strings.Join(strings.Fields(item.LastMessagePreview), " "),
			80,
		)
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) FindConversation(
	ctx context.Context,
	userID string,
	id string,
) (conversation.Conversation, error) {
	var item conversation.Conversation
	err := s.pool.QueryRow(ctx, `
		SELECT
			id::text, user_id::text, title, agent_name, status,
			last_message_at, created_at, updated_at
		FROM app_core.conversations
		WHERE id = $1
			AND user_id = $2
			AND deleted_at IS NULL
			AND status <> 'deleted'
	`, id, userID).Scan(
		&item.ID,
		&item.UserID,
		&item.Title,
		&item.AgentName,
		&item.Status,
		&item.LastMessageAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	return item, mapConversationError(err)
}

func (s *Store) UpdateConversationTitle(
	ctx context.Context,
	userID string,
	id string,
	title string,
) (conversation.Conversation, error) {
	var item conversation.Conversation
	err := s.pool.QueryRow(ctx, `
		UPDATE app_core.conversations
		SET title = $3, updated_at = NOW()
		WHERE id = $1
			AND user_id = $2
			AND deleted_at IS NULL
			AND status <> 'deleted'
		RETURNING
			id::text, user_id::text, title, agent_name, status,
			last_message_at, created_at, updated_at
	`, id, userID, title).Scan(
		&item.ID,
		&item.UserID,
		&item.Title,
		&item.AgentName,
		&item.Status,
		&item.LastMessageAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	return item, mapConversationError(err)
}

func (s *Store) DeleteConversation(
	ctx context.Context,
	userID string,
	id string,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.conversations c
		SET status = 'deleted', deleted_at = NOW(), updated_at = NOW()
		WHERE c.id = $1
			AND c.user_id = $2
			AND c.deleted_at IS NULL
			AND NOT EXISTS (
				SELECT 1
				FROM app_core.agent_runs r
				WHERE r.conversation_id = c.id
					AND r.status IN ('queued', 'running', 'cancel_requested')
			)
	`, id, userID)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		var active bool
		err := s.pool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1
				FROM app_core.conversations c
				JOIN app_core.agent_runs r ON r.conversation_id = c.id
				WHERE c.id = $1 AND c.user_id = $2
					AND c.deleted_at IS NULL
					AND r.status IN ('queued', 'running', 'cancel_requested')
			)
		`, id, userID).Scan(&active)
		if err != nil {
			return err
		}
		if active {
			return conversation.ErrGenerationActive
		}
		return conversation.ErrNotFound
	}
	return nil
}

func (s *Store) ListMessages(
	ctx context.Context,
	params conversation.MessageListParams,
) ([]conversation.Message, error) {
	var exists bool
	if err := s.pool.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM app_core.conversations
			WHERE id = $1 AND user_id = $2
				AND deleted_at IS NULL AND status <> 'deleted'
		)
	`, params.ConversationID, params.UserID).Scan(&exists); err != nil {
		return nil, err
	}
	if !exists {
		return nil, conversation.ErrNotFound
	}

	rows, err := s.pool.Query(ctx, `
		SELECT
			m.id::text,
			m.conversation_id::text,
			m.client_message_id::text,
			m.role,
			m.content,
			m.status,
			m.sequence_id,
			m.metadata,
			m.created_at,
			m.updated_at,
			m.completed_at
		FROM app_core.messages m
		WHERE m.conversation_id = $1
			AND ($2::bigint IS NULL OR m.sequence_id < $2)
		ORDER BY m.sequence_id DESC
		LIMIT $3
	`, params.ConversationID, params.BeforeSequence, params.Limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	reversed := make([]conversation.Message, 0, params.Limit)
	for rows.Next() {
		item, err := scanMessage(rows)
		if err != nil {
			return nil, err
		}
		reversed = append(reversed, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for left, right := 0, len(reversed)-1; left < right; left, right = left+1, right-1 {
		reversed[left], reversed[right] = reversed[right], reversed[left]
	}
	return reversed, nil
}

func (s *Store) StartGeneration(
	ctx context.Context,
	params conversation.StartGenerationParams,
) (conversation.Generation, error) {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return conversation.Generation{}, err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	var result conversation.Generation
	err = transaction.QueryRow(ctx, `
		SELECT
			id::text, user_id::text, title, agent_name, status,
			last_message_at, created_at, updated_at
		FROM app_core.conversations
		WHERE id = $1
			AND user_id = $2
			AND deleted_at IS NULL
			AND status = 'active'
		FOR UPDATE
	`, params.ConversationID, params.UserID).Scan(
		&result.Conversation.ID,
		&result.Conversation.UserID,
		&result.Conversation.Title,
		&result.Conversation.AgentName,
		&result.Conversation.Status,
		&result.Conversation.LastMessageAt,
		&result.Conversation.CreatedAt,
		&result.Conversation.UpdatedAt,
	)
	if err != nil {
		return conversation.Generation{}, mapConversationError(err)
	}

	var duplicate bool
	if err := transaction.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM app_core.messages
			WHERE conversation_id = $1 AND client_message_id = $2
		)
	`, params.ConversationID, params.ClientMessageID).Scan(&duplicate); err != nil {
		return conversation.Generation{}, err
	}
	if duplicate {
		return conversation.Generation{}, conversation.ErrDuplicateMessage
	}

	now := time.Now().UTC()
	userMessageID := newPostgresID()
	assistantMessageID := newPostgresID()
	runID := newPostgresID()

	err = transaction.QueryRow(ctx, `
		INSERT INTO app_core.messages (
			id, conversation_id, client_message_id, role, content,
			status, completed_at
		)
		VALUES ($1, $2, $3, 'user', $4, 'completed', $5)
		RETURNING
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
	`, userMessageID, params.ConversationID, params.ClientMessageID, params.Content, now).
		Scan(messageScanTargets(&result.UserMessage)...)
	if err != nil {
		return conversation.Generation{}, mapConversationError(err)
	}

	err = transaction.QueryRow(ctx, `
		INSERT INTO app_core.messages (
			id, conversation_id, role, content, status
		)
		VALUES ($1, $2, 'assistant', '', 'streaming')
		RETURNING
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
	`, assistantMessageID, params.ConversationID).
		Scan(messageScanTargets(&result.Assistant)...)
	if err != nil {
		return conversation.Generation{}, err
	}

	agentName := params.AgentName
	if agentName == "" {
		agentName = result.Conversation.AgentName
	}
	_, err = transaction.Exec(ctx, `
		INSERT INTO app_core.agent_runs (
			id, conversation_id, user_message_id, assistant_message_id,
			request_id, execution_id, idempotency_key, agent_name,
			protocol_version, status, trace_id
		)
		VALUES ($1, $2, $3, $4, $5, $6, $6, $7, $8, 'queued', $6)
	`,
		runID,
		params.ConversationID,
		userMessageID,
		assistantMessageID,
		params.RequestID,
		params.ExecutionID,
		agentName,
		params.ProtocolVersion,
	)
	if err != nil {
		var pgError *pgconn.PgError
		if errors.As(err, &pgError) && pgError.Code == "23505" {
			return conversation.Generation{}, conversation.ErrGenerationActive
		}
		return conversation.Generation{}, err
	}

	title := result.Conversation.Title
	if title == conversation.DefaultTitle && result.Conversation.LastMessageAt == nil {
		title = conversation.BuildTitle(params.Content)
	}
	err = transaction.QueryRow(ctx, `
		UPDATE app_core.conversations
		SET title = $2,
			agent_name = $3,
			last_message_at = $4,
			updated_at = $4
		WHERE id = $1
		RETURNING
			id::text, user_id::text, title, agent_name, status,
			last_message_at, created_at, updated_at
	`, params.ConversationID, title, agentName, now).Scan(
		&result.Conversation.ID,
		&result.Conversation.UserID,
		&result.Conversation.Title,
		&result.Conversation.AgentName,
		&result.Conversation.Status,
		&result.Conversation.LastMessageAt,
		&result.Conversation.CreatedAt,
		&result.Conversation.UpdatedAt,
	)
	if err != nil {
		return conversation.Generation{}, err
	}

	result.Run = conversation.Run{
		ID:                 runID,
		ExecutionID:        params.ExecutionID,
		ConversationID:     params.ConversationID,
		UserMessageID:      userMessageID,
		AssistantMessageID: assistantMessageID,
		RequestID:          params.RequestID,
		AgentName:          agentName,
		Status:             "queued",
		ProtocolVersion:    params.ProtocolVersion,
	}
	if err := transaction.Commit(ctx); err != nil {
		return conversation.Generation{}, err
	}
	return result, nil
}

func (s *Store) LoadHistory(
	ctx context.Context,
	userID string,
	conversationID string,
	limit int,
	maxCharacters int,
) ([]conversation.Message, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT
			m.id::text,
			m.conversation_id::text,
			m.client_message_id::text,
			m.role,
			m.content,
			m.status,
			m.sequence_id,
			m.metadata,
			m.created_at,
			m.updated_at,
			m.completed_at
		FROM app_core.messages m
		JOIN app_core.conversations c ON c.id = m.conversation_id
		WHERE c.id = $1
			AND c.user_id = $2
			AND c.deleted_at IS NULL
			AND m.content <> ''
			AND (
				m.status = 'completed'
				OR (m.role = 'assistant' AND m.status = 'stopped')
			)
		ORDER BY m.sequence_id DESC
		LIMIT $3
	`, conversationID, userID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]conversation.Message, 0, limit)
	total := 0
	for rows.Next() {
		item, err := scanMessage(rows)
		if err != nil {
			return nil, err
		}
		if total+len([]rune(item.Content)) > maxCharacters && len(items) > 0 {
			break
		}
		total += len([]rune(item.Content))
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	for left, right := 0, len(items)-1; left < right; left, right = left+1, right-1 {
		items[left], items[right] = items[right], items[left]
	}
	return items, nil
}

func (s *Store) CheckpointGeneration(
	ctx context.Context,
	userID string,
	assistantMessageID string,
	content string,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.messages m
		SET content = $3, updated_at = NOW()
		FROM app_core.conversations c
		WHERE m.id = $1
			AND m.conversation_id = c.id
			AND c.user_id = $2
			AND m.role = 'assistant'
			AND m.status = 'streaming'
	`, assistantMessageID, userID, content)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrNotFound
	}
	return nil
}

func (s *Store) FinishGeneration(
	ctx context.Context,
	params conversation.FinishGenerationParams,
) error {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	var conversationID string
	err = transaction.QueryRow(ctx, `
		UPDATE app_core.messages m
		SET content = $3,
			status = $4,
			updated_at = $5,
			completed_at = $5
		FROM app_core.conversations c
		WHERE m.id = $1
			AND m.conversation_id = c.id
			AND c.user_id = $2
			AND m.role = 'assistant'
			AND m.status = 'streaming'
		RETURNING m.conversation_id::text
	`,
		params.AssistantMessageID,
		params.UserID,
		params.Content,
		messageStatus(params.Status),
		params.GenerationCompleted,
	).Scan(&conversationID)
	if errors.Is(err, pgx.ErrNoRows) {
		return conversation.ErrNotFound
	}
	if err != nil {
		return err
	}

	_, err = transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET status = CASE
				WHEN status IN ('completed', 'cancelled', 'failed', 'timed_out')
					THEN status
				ELSE $2
			END,
			error_code = NULLIF($3, ''),
			error_detail = NULLIF($4, ''),
			first_token_at = COALESCE(first_token_at, $5),
			completed_at = COALESCE(completed_at, $6)
		WHERE id = $1
	`,
		params.RunID,
		runStatus(params.Status),
		params.ErrorCode,
		truncateRunes(params.ErrorDetail, 1000),
		params.FirstTokenAt,
		params.GenerationCompleted,
	)
	if err != nil {
		return err
	}
	_, err = transaction.Exec(ctx, `
		UPDATE app_core.conversations
		SET last_message_at = $2, updated_at = $2
		WHERE id = $1
	`, conversationID, params.GenerationCompleted)
	if err != nil {
		return err
	}
	return transaction.Commit(ctx)
}

func (s *Store) RecordAgentEvent(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
) (bool, error) {
	if event.TraceID == "" {
		event.TraceID = event.ExecutionID
	}
	if event.Category == "" {
		event.Category = strings.SplitN(event.Type, ".", 2)[0]
	}
	if event.EventSchemaVersion < 1 {
		event.EventSchemaVersion = 1
	}
	event.ContentCapture = agenttrace.CaptureLevel(event.ContentCapture)
	event.Data = agenttrace.Sanitize(event.Data)

	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return false, err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	command, err := transaction.Exec(ctx, `
		INSERT INTO app_core.agent_run_events (
			run_id, execution_id, sequence, event_type, occurred_at,
			trace_id, span_id, parent_span_id, category, stage,
			event_schema_version, content_capture_level, data
		)
		SELECT
			r.id, $3, $4, $5, $6,
			$7, NULLIF($8, ''), NULLIF($9, ''), $10, NULLIF($11, ''),
			$12, $13, $14
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1
			AND c.user_id = $2
			AND r.execution_id = $3
		ON CONFLICT (execution_id, sequence) DO NOTHING
	`,
		runID,
		userID,
		event.ExecutionID,
		event.Sequence,
		event.Type,
		event.OccurredAt,
		event.TraceID,
		event.SpanID,
		event.ParentSpanID,
		event.Category,
		event.Stage,
		event.EventSchemaVersion,
		event.ContentCapture,
		event.Data,
	)
	if err != nil {
		return false, err
	}
	if command.RowsAffected() == 0 {
		var exists bool
		if err := transaction.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1
				FROM app_core.agent_runs r
				JOIN app_core.conversations c ON c.id = r.conversation_id
				WHERE r.id = $1 AND c.user_id = $2
					AND r.execution_id = $3
			)
		`, runID, userID, event.ExecutionID).Scan(&exists); err != nil {
			return false, err
		}
		if !exists {
			return false, conversation.ErrNotFound
		}
		return false, transaction.Commit(ctx)
	}

	status := statusForEvent(event.Type)
	_, err = transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET last_sequence = GREATEST(last_sequence, $2),
			status = CASE
				WHEN status IN ('completed', 'cancelled', 'failed', 'timed_out')
					THEN status
				WHEN $3 = '' THEN status
				ELSE $3
			END,
			service_version = COALESCE(
				NULLIF($4::jsonb->>'service_version', ''),
				service_version
			),
			actual_route = COALESCE(
				NULLIF($4::jsonb->>'actual_route', ''),
				NULLIF($4::jsonb->>'selected_workflow', ''),
				NULLIF($4::jsonb->>'workflow_name', ''),
				actual_route
			),
			model_name = COALESCE(
				NULLIF($4::jsonb->>'model_name', ''),
				model_name
			),
			agent_version = COALESCE(
				NULLIF($4::jsonb->>'agent_version', ''),
				agent_version
			),
			graph_version = COALESCE(
				NULLIF($4::jsonb->>'graph_version', ''),
				graph_version
			),
			prompt_bundle_hash = COALESCE(
				NULLIF($4::jsonb->>'prompt_bundle_hash', ''),
				prompt_bundle_hash
			),
			error_code = CASE
				WHEN $3 IN ('failed', 'timed_out')
					THEN NULLIF($4::jsonb->>'code', '')
				ELSE error_code
			END,
			error_detail = CASE
				WHEN $3 IN ('failed', 'timed_out')
					THEN LEFT(COALESCE($4::jsonb->>'message', ''), 1000)
				ELSE error_detail
			END,
			started_at = CASE
				WHEN $3 = 'running' THEN LEAST(started_at, $5)
				ELSE started_at
			END,
			completed_at = CASE
				WHEN $3 IN ('completed', 'cancelled', 'failed', 'timed_out')
					THEN COALESCE(completed_at, $5)
				ELSE completed_at
			END,
			trace_id = COALESCE(NULLIF($6, ''), trace_id)
		WHERE id = $1
	`,
		runID,
		event.Sequence,
		status,
		event.Data,
		event.OccurredAt,
		event.TraceID,
	)
	if err != nil {
		return false, err
	}
	if err := projectAgentEvent(ctx, transaction, runID, event); err != nil {
		return false, err
	}
	return true, transaction.Commit(ctx)
}

func scanRunSummary(row rowScanner) (conversation.RunSummary, error) {
	var item conversation.RunSummary
	err := row.Scan(
		&item.ID,
		&item.ExecutionID,
		&item.TraceID,
		&item.ConversationID,
		&item.AgentName,
		&item.ActualRoute,
		&item.ModelName,
		&item.Status,
		&item.ProtocolVersion,
		&item.ServiceVersion,
		&item.AgentVersion,
		&item.GraphVersion,
		&item.PromptBundleHash,
		&item.InputTokens,
		&item.OutputTokens,
		&item.CachedTokens,
		&item.TotalTokens,
		&item.ModelCallCount,
		&item.ToolCallCount,
		&item.RetrievalCount,
		&item.TotalDurationMS,
		&item.ErrorCode,
		&item.ErrorDetail,
		&item.FirstTokenAt,
		&item.StartedAt,
		&item.CompletedAt,
		&item.CreatedAt,
	)
	return item, err
}

const runSummaryColumns = `
	r.id::text,
	r.execution_id,
	r.trace_id,
	r.conversation_id::text,
	r.agent_name,
	r.actual_route,
	r.model_name,
	r.status,
	r.protocol_version,
	r.service_version,
	r.agent_version,
	r.graph_version,
	r.prompt_bundle_hash,
	r.input_tokens,
	r.output_tokens,
	r.cached_tokens,
	r.total_tokens,
	r.model_call_count,
	r.tool_call_count,
	r.retrieval_count,
	r.total_duration_ms,
	r.error_code,
	r.error_detail,
	r.first_token_at,
	r.started_at,
	r.completed_at,
	r.started_at
`

func (s *Store) ListAgentRuns(
	ctx context.Context,
	params conversation.RunListParams,
) ([]conversation.RunSummary, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT `+runSummaryColumns+`
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE c.user_id = $1
			AND ($2 = '' OR r.status = $2)
			AND ($3::timestamptz IS NULL OR r.started_at < $3)
		ORDER BY r.started_at DESC, r.id DESC
		LIMIT $4
	`, params.UserID, params.Status, params.Before, params.Limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]conversation.RunSummary, 0, params.Limit)
	for rows.Next() {
		item, scanErr := scanRunSummary(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) FindAgentRunDetail(
	ctx context.Context,
	userID string,
	runID string,
) (conversation.RunDetail, error) {
	detail := conversation.RunDetail{
		Spans:   []conversation.RunSpan{},
		Events:  []conversation.RunEvent{},
		Prompts: []conversation.RunPrompt{},
	}
	item, err := scanRunSummary(s.pool.QueryRow(ctx, `
		SELECT `+runSummaryColumns+`
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1 AND c.user_id = $2
	`, runID, userID))
	if errors.Is(err, pgx.ErrNoRows) {
		return detail, conversation.ErrNotFound
	}
	if err != nil {
		return detail, err
	}
	detail.Run = item

	spanRows, err := s.pool.Query(ctx, `
		SELECT
			span_id, parent_span_id, span_type, name, stage, status,
			started_at, completed_at, duration_ms,
			input_tokens, output_tokens, cached_tokens, total_tokens,
			error_code, attributes
		FROM app_core.agent_run_spans
		WHERE run_id = $1
		ORDER BY started_at, id
	`, runID)
	if err != nil {
		return detail, err
	}
	defer spanRows.Close()
	for spanRows.Next() {
		var span conversation.RunSpan
		if err := spanRows.Scan(
			&span.SpanID,
			&span.ParentSpanID,
			&span.Type,
			&span.Name,
			&span.Stage,
			&span.Status,
			&span.StartedAt,
			&span.CompletedAt,
			&span.DurationMS,
			&span.InputTokens,
			&span.OutputTokens,
			&span.CachedTokens,
			&span.TotalTokens,
			&span.ErrorCode,
			&span.Attributes,
		); err != nil {
			return detail, err
		}
		detail.Spans = append(detail.Spans, span)
	}
	if err := spanRows.Err(); err != nil {
		return detail, err
	}

	eventRows, err := s.pool.Query(ctx, `
		SELECT
			sequence, event_type, occurred_at, trace_id, span_id,
			parent_span_id, category, stage, event_schema_version,
			content_capture_level, data
		FROM app_core.agent_run_events
		WHERE run_id = $1
		ORDER BY sequence
	`, runID)
	if err != nil {
		return detail, err
	}
	defer eventRows.Close()
	for eventRows.Next() {
		var event conversation.RunEvent
		if err := eventRows.Scan(
			&event.Sequence,
			&event.Type,
			&event.OccurredAt,
			&event.TraceID,
			&event.SpanID,
			&event.ParentSpanID,
			&event.Category,
			&event.Stage,
			&event.EventSchemaVersion,
			&event.ContentCaptureLevel,
			&event.Data,
		); err != nil {
			return detail, err
		}
		detail.Events = append(detail.Events, event)
	}
	if err := eventRows.Err(); err != nil {
		return detail, err
	}

	promptRows, err := s.pool.Query(ctx, `
		SELECT
			p.sequence, p.stage, a.relative_path, p.prompt_hash,
			p.rendered_hash, p.rendered_characters, p.iteration
		FROM app_core.agent_run_prompts p
		JOIN app_core.prompt_artifacts a
			ON a.prompt_hash = p.prompt_hash
		WHERE p.run_id = $1
		ORDER BY p.sequence
	`, runID)
	if err != nil {
		return detail, err
	}
	defer promptRows.Close()
	for promptRows.Next() {
		var prompt conversation.RunPrompt
		if err := promptRows.Scan(
			&prompt.Sequence,
			&prompt.Stage,
			&prompt.Path,
			&prompt.PromptHash,
			&prompt.RenderedHash,
			&prompt.RenderedCharacters,
			&prompt.Iteration,
		); err != nil {
			return detail, err
		}
		detail.Prompts = append(detail.Prompts, prompt)
	}
	if err := promptRows.Err(); err != nil {
		return detail, err
	}
	return detail, nil
}

func projectAgentEvent(
	ctx context.Context,
	transaction pgx.Tx,
	runID string,
	event agent.Event,
) error {
	switch event.Type {
	case "prompt.used":
		if _, err := transaction.Exec(ctx, `
			INSERT INTO app_core.prompt_artifacts (
				prompt_hash, relative_path, metadata
			)
			SELECT
				$1::jsonb->>'sha256',
				COALESCE(NULLIF($1::jsonb->>'path', ''), 'unknown'),
				jsonb_build_object(
					'content_capture_level',
					COALESCE($1::jsonb->>'content_capture_level', 'hashed')
				)
			WHERE COALESCE($1::jsonb->>'sha256', '') <> ''
			ON CONFLICT (prompt_hash) DO UPDATE
			SET relative_path = EXCLUDED.relative_path
		`, event.Data); err != nil {
			return err
		}
		_, err := transaction.Exec(ctx, `
			INSERT INTO app_core.agent_run_prompts (
				run_id, sequence, prompt_hash, stage,
				rendered_hash, rendered_characters, iteration
			)
			SELECT
				$1,
				$2,
				$3::jsonb->>'sha256',
				COALESCE(NULLIF($3::jsonb->>'stage', ''), 'unknown'),
				NULLIF($3::jsonb->>'rendered_sha256', ''),
				NULLIF($3::jsonb->>'rendered_characters', '')::integer,
				NULLIF($3::jsonb->>'iteration', '')::integer
			WHERE COALESCE($3::jsonb->>'sha256', '') <> ''
			ON CONFLICT (run_id, sequence) DO NOTHING
		`, runID, event.Sequence, event.Data)
		return err
	case "model.started", "model.completed", "model.failed", "model.cancelled",
		"tool.started", "tool.completed", "tool.failed", "tool.cancelled":
		if event.SpanID == "" {
			return nil
		}
		status := strings.TrimPrefix(
			event.Type,
			strings.SplitN(event.Type, ".", 2)[0]+".",
		)
		spanType := strings.SplitN(event.Type, ".", 2)[0]
		_, err := transaction.Exec(ctx, `
			INSERT INTO app_core.agent_run_spans (
				run_id, execution_id, trace_id, span_id, parent_span_id,
				span_type, name, stage, status, started_at, completed_at,
				duration_ms, input_tokens, output_tokens, cached_tokens,
				total_tokens, error_code, attributes
			)
			VALUES (
				$1, $2, $3, $4, NULLIF($5, ''),
				$6,
				COALESCE(NULLIF($7::jsonb->>'name', ''), 'unknown'),
				NULLIF(COALESCE($8, $7::jsonb->>'stage'), ''),
				$9,
				CASE
					WHEN $9 = 'started' THEN $10::timestamptz
					ELSE $10::timestamptz - (
						COALESCE(NULLIF($7::jsonb->>'duration_ms', '')::bigint, 0)
						* INTERVAL '1 millisecond'
					)
				END,
				CASE
					WHEN $9 = 'started' THEN NULL
					ELSE $10::timestamptz
				END,
				NULLIF($7::jsonb->>'duration_ms', '')::bigint,
				COALESCE(NULLIF($7::jsonb->>'input_tokens', '')::bigint, 0),
				COALESCE(NULLIF($7::jsonb->>'output_tokens', '')::bigint, 0),
				COALESCE(NULLIF($7::jsonb->>'cached_tokens', '')::bigint, 0),
				COALESCE(NULLIF($7::jsonb->>'total_tokens', '')::bigint, 0),
				NULLIF($7::jsonb->>'error_code', ''),
				$7
			)
			ON CONFLICT (execution_id, span_id) DO UPDATE
			SET status = EXCLUDED.status,
				completed_at = COALESCE(
					EXCLUDED.completed_at,
					app_core.agent_run_spans.completed_at
				),
				duration_ms = COALESCE(
					EXCLUDED.duration_ms,
					app_core.agent_run_spans.duration_ms
				),
				input_tokens = EXCLUDED.input_tokens,
				output_tokens = EXCLUDED.output_tokens,
				cached_tokens = EXCLUDED.cached_tokens,
				total_tokens = EXCLUDED.total_tokens,
				error_code = COALESCE(
					EXCLUDED.error_code,
					app_core.agent_run_spans.error_code
				),
				attributes = app_core.agent_run_spans.attributes || EXCLUDED.attributes
		`,
			runID,
			event.ExecutionID,
			event.TraceID,
			event.SpanID,
			event.ParentSpanID,
			spanType,
			event.Data,
			event.Stage,
			status,
			event.OccurredAt,
		)
		if err != nil {
			return err
		}
		if event.Type == "tool.started" {
			_, err = transaction.Exec(ctx, `
				UPDATE app_core.agent_runs
				SET tool_call_count = tool_call_count + 1
				WHERE id = $1
			`, runID)
			return err
		}
		if spanType == "model" && status != "started" {
			_, err = transaction.Exec(ctx, `
				UPDATE app_core.agent_runs
				SET model_call_count = model_call_count + 1,
					input_tokens = input_tokens
						+ COALESCE(NULLIF($2::jsonb->>'input_tokens', '')::bigint, 0),
					output_tokens = output_tokens
						+ COALESCE(NULLIF($2::jsonb->>'output_tokens', '')::bigint, 0),
					cached_tokens = cached_tokens
						+ COALESCE(NULLIF($2::jsonb->>'cached_tokens', '')::bigint, 0),
					total_tokens = total_tokens
						+ COALESCE(NULLIF($2::jsonb->>'total_tokens', '')::bigint, 0)
				WHERE id = $1
			`, runID, event.Data)
		}
		return err
	case "usage":
		_, err := transaction.Exec(ctx, `
			UPDATE app_core.agent_runs
			SET agent_version = COALESCE(
					NULLIF($2::jsonb->>'agent_version', ''),
					agent_version
				),
				graph_version = COALESCE(
					NULLIF($2::jsonb->>'graph_version', ''),
					graph_version
				),
				prompt_bundle_hash = COALESCE(
					NULLIF($2::jsonb->>'prompt_bundle_hash', ''),
					prompt_bundle_hash
				),
				model_name = COALESCE(
					NULLIF($2::jsonb->>'model_name', ''),
					model_name
				),
				input_tokens = GREATEST(
					input_tokens,
					COALESCE(NULLIF($2::jsonb->>'input_tokens', '')::bigint, 0)
				),
				output_tokens = GREATEST(
					output_tokens,
					COALESCE(NULLIF($2::jsonb->>'output_tokens', '')::bigint, 0)
				),
				cached_tokens = GREATEST(
					cached_tokens,
					COALESCE(NULLIF($2::jsonb->>'cached_tokens', '')::bigint, 0)
				),
				total_tokens = GREATEST(
					total_tokens,
					COALESCE(NULLIF($2::jsonb->>'total_tokens', '')::bigint, 0)
				),
				total_duration_ms = COALESCE(
					NULLIF($2::jsonb->>'total_ms', '')::bigint,
					total_duration_ms
				)
			WHERE id = $1
		`, runID, event.Data)
		return err
	default:
		return nil
	}
}

func (s *Store) MarkSequenceGap(
	ctx context.Context,
	userID string,
	runID string,
	expected int64,
	received int64,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs r
		SET metadata = jsonb_set(
			metadata,
			'{reconciliation}',
			jsonb_build_object(
				'required', true,
				'expected_sequence', $3::bigint,
				'received_sequence', $4::bigint,
				'detected_at', NOW()
			),
			true
		)
		FROM app_core.conversations c
		WHERE r.id = $1 AND c.id = r.conversation_id AND c.user_id = $2
	`, runID, userID, expected, received)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrNotFound
	}
	return nil
}

func (s *Store) MarkSequenceReconciled(
	ctx context.Context,
	userID string,
	runID string,
	resolvedSequence int64,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs r
		SET metadata = jsonb_set(
			metadata,
			'{reconciliation}',
			COALESCE(metadata->'reconciliation', '{}'::jsonb)
				|| jsonb_build_object(
					'required', false,
					'resolved_sequence', $3::bigint,
					'resolved_at', NOW()
				),
			true
		)
		FROM app_core.conversations c
		WHERE r.id = $1 AND c.id = r.conversation_id AND c.user_id = $2
	`, runID, userID, resolvedSequence)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrNotFound
	}
	return nil
}

func (s *Store) RequestRunCancellation(
	ctx context.Context,
	userID string,
	runID string,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs r
		SET status = 'cancel_requested',
			metadata = jsonb_set(
				metadata,
				'{cancel_requested_at}',
				to_jsonb(NOW()),
				true
			)
		FROM app_core.conversations c
		WHERE r.id = $1
			AND c.id = r.conversation_id
			AND c.user_id = $2
			AND r.status IN ('queued', 'running', 'cancel_requested')
	`, runID, userID)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		var exists bool
		if err := s.pool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1
				FROM app_core.agent_runs r
				JOIN app_core.conversations c ON c.id = r.conversation_id
				WHERE r.id = $1 AND c.user_id = $2
			)
		`, runID, userID).Scan(&exists); err != nil {
			return err
		}
		if !exists {
			return conversation.ErrNotFound
		}
	}
	return nil
}

func (s *Store) InterruptStaleGenerations(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
		WITH stale AS (
			UPDATE app_core.agent_runs
			SET status = 'failed',
				error_code = 'generation_interrupted',
				error_detail = 'Generation did not finish before the service restarted',
				completed_at = NOW()
			WHERE status IN ('queued', 'running', 'cancel_requested')
			RETURNING assistant_message_id
		)
		UPDATE app_core.messages m
		SET status = 'failed', updated_at = NOW(), completed_at = NOW()
		FROM stale
		WHERE m.id = stale.assistant_message_id
			AND m.status = 'streaming'
	`)
	return err
}

type rowScanner interface {
	Scan(...any) error
}

func scanMessage(row rowScanner) (conversation.Message, error) {
	var item conversation.Message
	err := row.Scan(messageScanTargets(&item)...)
	return item, err
}

func messageScanTargets(item *conversation.Message) []any {
	return []any{
		&item.ID,
		&item.ConversationID,
		&item.ClientMessageID,
		&item.Role,
		&item.Content,
		&item.Status,
		&item.SequenceID,
		&item.Metadata,
		&item.CreatedAt,
		&item.UpdatedAt,
		&item.CompletedAt,
	}
}

func mapConversationError(err error) error {
	if errors.Is(err, pgx.ErrNoRows) {
		return conversation.ErrNotFound
	}
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) {
		switch pgError.Code {
		case "22P02", "23503":
			return conversation.ErrInvalidInput
		}
	}
	return err
}

func truncateRunes(value string, max int) string {
	runes := []rune(value)
	if len(runes) <= max {
		return value
	}
	return string(runes[:max])
}

func statusForEvent(eventType string) string {
	switch eventType {
	case "run.started":
		return string(agent.StatusRunning)
	case "run.cancel_requested":
		return string(agent.StatusCancelRequested)
	case "run.completed":
		return string(agent.StatusCompleted)
	case "run.cancelled":
		return string(agent.StatusCancelled)
	case "run.failed":
		return string(agent.StatusFailed)
	case "run.timed_out":
		return string(agent.StatusTimedOut)
	default:
		return ""
	}
}

func runStatus(status string) string {
	if status == "stopped" {
		return string(agent.StatusCancelled)
	}
	return status
}

func messageStatus(status string) string {
	if status == string(agent.StatusCancelled) || status == string(agent.StatusTimedOut) {
		return "stopped"
	}
	return status
}

func newPostgresID() string {
	return auth.NewID()
}
