package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/agenttrace"
	"github.com/starslittle/agent/go-backend/internal/auth"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
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

	if params.Idempotent {
		existing, found, existingErr := loadIdempotentGeneration(
			ctx,
			transaction,
			params,
			result.Conversation,
		)
		if existingErr != nil {
			return conversation.Generation{}, existingErr
		}
		if found {
			existing.Replayed = true
			if err := transaction.Commit(ctx); err != nil {
				return conversation.Generation{}, err
			}
			return existing, nil
		}
	} else {
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
			model_id, requested_skill,
			protocol_version, status, trace_id, metadata
		)
		VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, 'queued', $6,
			jsonb_build_object('run_supervisor_managed', $12::boolean)
		)
	`,
		runID,
		params.ConversationID,
		userMessageID,
		assistantMessageID,
		params.RequestID,
		params.ExecutionID,
		params.IdempotencyKey,
		agentName,
		params.ModelID,
		params.RequestedSkill,
		params.ProtocolVersion,
		params.SupervisorManaged,
	)
	if err != nil {
		var pgError *pgconn.PgError
		if errors.As(err, &pgError) && pgError.Code == "23505" {
			if pgError.ConstraintName == "agent_runs_idempotency_key_idx" {
				return conversation.Generation{}, conversation.ErrIdempotencyConflict
			}
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
		IdempotencyKey:     params.IdempotencyKey,
		ConversationID:     params.ConversationID,
		UserMessageID:      userMessageID,
		AssistantMessageID: assistantMessageID,
		RequestID:          params.RequestID,
		AgentName:          agentName,
		ModelID:            params.ModelID,
		RequestedSkill:     params.RequestedSkill,
		ResolvedSkills:     json.RawMessage(`null`),
		Status:             "queued",
		ProtocolVersion:    params.ProtocolVersion,
	}
	if err := transaction.Commit(ctx); err != nil {
		return conversation.Generation{}, err
	}
	return result, nil
}

func loadIdempotentGeneration(
	ctx context.Context,
	transaction pgx.Tx,
	params conversation.StartGenerationParams,
	item conversation.Conversation,
) (conversation.Generation, bool, error) {
	var (
		run              conversation.Run
		existingClientID string
		existingContent  string
		existingAgent    string
	)
	err := transaction.QueryRow(ctx, `
		SELECT
			r.id::text,
			r.execution_id,
			r.idempotency_key,
			r.conversation_id::text,
			r.user_message_id::text,
			r.assistant_message_id::text,
			r.request_id,
			r.agent_name,
			r.model_id,
			r.requested_skill,
			COALESCE(r.resolved_skills, 'null'::jsonb),
			r.primary_skill,
			r.selection_source,
			r.context_package_id::text,
			r.status,
			r.protocol_version,
			r.last_sequence,
			um.client_message_id::text,
			um.content,
			r.agent_name
		FROM app_core.agent_runs r
		JOIN app_core.messages um ON um.id = r.user_message_id
		WHERE r.conversation_id = $1
			AND (
				um.client_message_id = $2
				OR r.idempotency_key = $3
			)
		ORDER BY
			CASE WHEN r.idempotency_key = $3 THEN 0 ELSE 1 END,
			r.started_at DESC
		LIMIT 1
		FOR UPDATE OF r
	`,
		params.ConversationID,
		params.ClientMessageID,
		params.IdempotencyKey,
	).Scan(
		&run.ID,
		&run.ExecutionID,
		&run.IdempotencyKey,
		&run.ConversationID,
		&run.UserMessageID,
		&run.AssistantMessageID,
		&run.RequestID,
		&run.AgentName,
		&run.ModelID,
		&run.RequestedSkill,
		&run.ResolvedSkills,
		&run.PrimarySkill,
		&run.SelectionSource,
		&run.ContextPackageID,
		&run.Status,
		&run.ProtocolVersion,
		&run.LastSequence,
		&existingClientID,
		&existingContent,
		&existingAgent,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return conversation.Generation{}, false, nil
	}
	if err != nil {
		return conversation.Generation{}, false, err
	}
	if existingClientID != params.ClientMessageID ||
		run.IdempotencyKey != params.IdempotencyKey ||
		existingContent != params.Content ||
		(params.AgentName != "" && existingAgent != params.AgentName) ||
		run.ModelID != params.ModelID ||
		!optionalStringEqual(run.RequestedSkill, params.RequestedSkill) {
		return conversation.Generation{}, false, conversation.ErrIdempotencyConflict
	}

	result := conversation.Generation{
		Conversation: item,
		Run:          run,
	}
	if err := transaction.QueryRow(ctx, `
		SELECT
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
		FROM app_core.messages
		WHERE id = $1
	`, run.UserMessageID).Scan(messageScanTargets(&result.UserMessage)...); err != nil {
		return conversation.Generation{}, false, err
	}
	if err := transaction.QueryRow(ctx, `
		SELECT
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
		FROM app_core.messages
		WHERE id = $1
	`, run.AssistantMessageID).Scan(messageScanTargets(&result.Assistant)...); err != nil {
		return conversation.Generation{}, false, err
	}
	return result, true, nil
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
) (string, error) {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return "", err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	var (
		currentRunStatus string
		leaseOwner       string
		leaseEpoch       int64
	)
	if params.Lease != nil {
		leaseOwner = params.Lease.OwnerID
		leaseEpoch = params.Lease.Epoch
	}
	err = transaction.QueryRow(ctx, `
		SELECT r.status
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1
			AND r.assistant_message_id = $2
			AND c.user_id = $3
			AND (
				$4 = ''
				OR (
					r.metadata->>'supervisor_owner_id' = $4
					AND (r.metadata->>'supervisor_lease_epoch')::bigint = $5
					AND (
						r.metadata->>'supervisor_lease_expires_at'
					)::timestamptz > NOW()
				)
			)
		FOR UPDATE OF r
	`,
		params.RunID,
		params.AssistantMessageID,
		params.UserID,
		leaseOwner,
		leaseEpoch,
	).Scan(&currentRunStatus)
	if errors.Is(err, pgx.ErrNoRows) {
		if params.Lease != nil {
			return "", conversation.ErrRunLeaseLost
		}
		return "", conversation.ErrNotFound
	}
	if err != nil {
		return "", err
	}

	requestedRunStatus := runStatus(params.Status)
	finalRunStatus := conversation.ResolveTerminalStatus(
		currentRunStatus,
		requestedRunStatus,
	)
	errorCode := params.ErrorCode
	if finalRunStatus == string(agent.StatusCancelled) &&
		requestedRunStatus == string(agent.StatusCompleted) &&
		errorCode == "" {
		errorCode = "generation_cancelled"
	}

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
		messageStatus(finalRunStatus),
		params.GenerationCompleted,
	).Scan(&conversationID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", conversation.ErrNotFound
	}
	if err != nil {
		return "", err
	}

	_, err = transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET status = $2,
			error_code = NULLIF($3, ''),
			error_detail = NULLIF($4, ''),
			first_token_at = COALESCE(first_token_at, $5),
			completed_at = COALESCE(completed_at, $6)
		WHERE id = $1
	`,
		params.RunID,
		finalRunStatus,
		errorCode,
		truncateRunes(params.ErrorDetail, 1000),
		params.FirstTokenAt,
		params.GenerationCompleted,
	)
	if err != nil {
		return "", err
	}
	_, err = transaction.Exec(ctx, `
		UPDATE app_core.conversations
		SET last_message_at = $2, updated_at = $2
		WHERE id = $1
	`, conversationID, params.GenerationCompleted)
	if err != nil {
		return "", err
	}
	if err := transaction.Commit(ctx); err != nil {
		return "", err
	}
	return finalRunStatus, nil
}

func (s *Store) RecordAgentEvent(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
) (bool, error) {
	return s.recordAgentEvent(ctx, userID, runID, event, nil)
}

func (s *Store) RecordAgentEventOwned(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
	lease conversation.RunLease,
) (bool, error) {
	return s.recordAgentEvent(ctx, userID, runID, event, &lease)
}

func (s *Store) recordAgentEvent(
	ctx context.Context,
	userID string,
	runID string,
	event agent.Event,
	lease *conversation.RunLease,
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

	var (
		leaseOwner string
		leaseEpoch int64
	)
	if lease != nil {
		leaseOwner = lease.OwnerID
		leaseEpoch = lease.Epoch
	}
	var lockedRunID string
	err = transaction.QueryRow(ctx, `
		SELECT r.id::text
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1
			AND c.user_id = $2
			AND r.execution_id = $3
			AND (
				$4 = ''
				OR (
					r.metadata->>'supervisor_owner_id' = $4
					AND (r.metadata->>'supervisor_lease_epoch')::bigint = $5
					AND (
						r.metadata->>'supervisor_lease_expires_at'
					)::timestamptz > NOW()
				)
			)
		FOR UPDATE OF r
	`, runID, userID, event.ExecutionID, leaseOwner, leaseEpoch).Scan(
		&lockedRunID,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		if lease != nil {
			return false, conversation.ErrRunLeaseLost
		}
		return false, conversation.ErrNotFound
	}
	if err != nil {
		return false, err
	}

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
	if event.Type == "run.resolved" {
		resolution, resolutionErr := agent.ParseSkillResolution(event.Data)
		if resolutionErr != nil {
			return false, resolutionErr
		}
		if resolutionErr = sealSkillResolution(
			ctx,
			transaction,
			runID,
			resolution,
		); resolutionErr != nil {
			return false, resolutionErr
		}
	}

	status := statusForEvent(event.Type)
	_, err = transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET last_sequence = GREATEST(last_sequence, $2),
			status = CASE
				WHEN status IN ('completed', 'cancelled', 'failed', 'timed_out')
					THEN status
				WHEN status = 'cancel_requested' AND $3 = 'completed'
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

func sealSkillResolution(
	ctx context.Context,
	transaction pgx.Tx,
	runID string,
	resolution agent.SkillResolution,
) error {
	resolved, err := json.Marshal(resolution.ResolvedSkills)
	if err != nil {
		return err
	}
	skillSnapshot := string(resolution.SkillSnapshot)
	if skillSnapshot == "" || skillSnapshot == "null" {
		skillSnapshot = "{}"
	}
	modelSnapshot := string(resolution.ModelSnapshot)
	command, err := transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET resolved_skills = CASE
				WHEN resolved_skills IS NULL THEN $4::jsonb
				ELSE resolved_skills
			END,
			primary_skill = CASE
				WHEN resolved_skills IS NULL THEN $5
				ELSE primary_skill
			END,
			selection_source = CASE
				WHEN resolved_skills IS NULL THEN $6
				ELSE selection_source
			END,
			skill_snapshot = CASE
				WHEN resolved_skills IS NULL THEN $7::jsonb
				ELSE skill_snapshot
			END,
			model_snapshot = CASE
				WHEN resolved_skills IS NULL THEN $8::jsonb
				ELSE model_snapshot
			END,
			context_package_id = CASE
				WHEN resolved_skills IS NULL THEN $9::uuid
				ELSE context_package_id
			END
		WHERE id = $1
			AND model_id = $2
			AND requested_skill IS NOT DISTINCT FROM $3
			AND (
				resolved_skills IS NULL OR (
					resolved_skills = $4::jsonb
					AND primary_skill IS NOT DISTINCT FROM $5
					AND selection_source = $6
					AND skill_snapshot = $7::jsonb
					AND model_snapshot = $8::jsonb
					AND context_package_id::text IS NOT DISTINCT FROM $9::text
				)
			)
	`,
		runID,
		resolution.ModelID,
		resolution.RequestedSkill,
		string(resolved),
		resolution.PrimarySkill,
		resolution.SelectionSource,
		skillSnapshot,
		modelSnapshot,
		resolution.ContextPackageID,
	)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrSkillResolutionConflict
	}
	return nil
}

func optionalStringEqual(left, right *string) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return *left == *right
}

func scanRunSummary(row rowScanner) (conversation.RunSummary, error) {
	var item conversation.RunSummary
	err := row.Scan(runSummaryScanTargets(&item)...)
	return item, err
}

func runSummaryScanTargets(item *conversation.RunSummary) []any {
	return []any{
		&item.ID,
		&item.ExecutionID,
		&item.TraceID,
		&item.ConversationID,
		&item.AgentName,
		&item.ModelID,
		&item.RequestedSkill,
		&item.ResolvedSkills,
		&item.PrimarySkill,
		&item.SelectionSource,
		&item.ContextPackageID,
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
	}
}

const runSummaryColumns = `
	r.id::text,
	r.execution_id,
	r.trace_id,
	r.conversation_id::text,
	r.agent_name,
	r.model_id,
	r.requested_skill,
	COALESCE(r.resolved_skills, 'null'::jsonb),
	r.primary_skill,
	r.selection_source,
	r.context_package_id::text,
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

func (s *Store) ListObservableAgentRuns(
	ctx context.Context,
	params conversation.ObservabilityRunListParams,
) ([]conversation.RunSummary, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT `+runSummaryColumns+`, c.user_id::text
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE ($1 = '' OR c.user_id = $1::uuid)
			AND (
				$2 = '' OR r.primary_skill = $2 OR r.requested_skill = $2 OR
				COALESCE(r.resolved_skills, '[]'::jsonb) @> to_jsonb(ARRAY[$2]::text[])
			)
			AND ($3 = '' OR r.actual_route = $3)
			AND ($4 = '' OR r.model_id = $4 OR r.model_name = $4)
			AND ($5 = '' OR r.status = $5)
			AND ($6 = '' OR r.error_code = $6)
			AND ($7::timestamptz IS NULL OR r.started_at >= $7)
			AND ($8::timestamptz IS NULL OR r.started_at <= $8)
			AND ($9::timestamptz IS NULL OR r.started_at < $9)
		ORDER BY r.started_at DESC, r.id DESC
		LIMIT $10
	`,
		params.UserID,
		params.Skill,
		params.Workflow,
		params.Model,
		params.Status,
		params.ErrorCode,
		params.From,
		params.To,
		params.Before,
		params.Limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	items := make([]conversation.RunSummary, 0, params.Limit)
	for rows.Next() {
		var item conversation.RunSummary
		targets := append(runSummaryScanTargets(&item), &item.OwnerUserID)
		if err := rows.Scan(targets...); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) FindObservableAgentRunDetail(
	ctx context.Context,
	runID string,
) (conversation.RunDetail, error) {
	var ownerUserID string
	err := s.pool.QueryRow(ctx, `
		SELECT c.user_id::text
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1
	`, runID).Scan(&ownerUserID)
	if errors.Is(err, pgx.ErrNoRows) {
		return conversation.RunDetail{}, conversation.ErrNotFound
	}
	if err != nil {
		return conversation.RunDetail{}, err
	}
	detail, err := s.FindAgentRunDetail(ctx, ownerUserID, runID)
	if err != nil {
		return detail, err
	}
	detail.Run.OwnerUserID = ownerUserID
	return detail, nil
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
	if detail.Run.ContextPackageID != nil {
		pkg, packageErr := s.FindContextPackageByRun(ctx, userID, runID)
		if packageErr != nil {
			return detail, packageErr
		}
		items := make([]contextpackage.UsageItem, 0, len(pkg.Items))
		for _, item := range pkg.Items {
			itemID, revisionID := item.ItemID, item.RevisionID
			items = append(items, contextpackage.UsageItem{ItemID: &itemID, RevisionID: &revisionID, Type: item.Type, Domain: item.Domain, Source: item.Source, UpdatedAt: item.UpdatedAt})
		}
		detail.ContextUsage = &contextpackage.Usage{PackageID: pkg.PackageID, RunID: runID, Purpose: pkg.Purpose, Items: items}
	}
	return detail, nil
}

func (s *Store) ListAgentRunEvents(
	ctx context.Context,
	userID string,
	runID string,
	startingAfter int64,
	limit int,
) (conversation.RunEventPage, error) {
	page := conversation.RunEventPage{Events: []agent.Event{}}
	err := s.pool.QueryRow(ctx, `
		SELECT
			r.execution_id,
			r.protocol_version,
			r.status,
			m.status,
			r.last_sequence,
			r.error_code
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		JOIN app_core.messages m ON m.id = r.assistant_message_id
		WHERE r.id = $1 AND c.user_id = $2
	`, runID, userID).Scan(
		&page.ExecutionID,
		&page.ProtocolVersion,
		&page.RunStatus,
		&page.AssistantStatus,
		&page.LastSequence,
		&page.ErrorCode,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return page, conversation.ErrNotFound
	}
	if err != nil {
		return page, err
	}

	rows, err := s.pool.Query(ctx, `
		SELECT
			sequence,
			event_type,
			occurred_at,
			COALESCE(trace_id, ''),
			COALESCE(span_id, ''),
			COALESCE(parent_span_id, ''),
			COALESCE(category, ''),
			COALESCE(stage, ''),
			event_schema_version,
			content_capture_level,
			data
		FROM app_core.agent_run_events
		WHERE run_id = $1 AND sequence > $2
		ORDER BY sequence
		LIMIT $3
	`, runID, startingAfter, limit)
	if err != nil {
		return page, err
	}
	defer rows.Close()
	for rows.Next() {
		event := agent.Event{
			ProtocolVersion: page.ProtocolVersion,
			ExecutionID:     page.ExecutionID,
			RunID:           runID,
		}
		if err := rows.Scan(
			&event.Sequence,
			&event.Type,
			&event.OccurredAt,
			&event.TraceID,
			&event.SpanID,
			&event.ParentSpanID,
			&event.Category,
			&event.Stage,
			&event.EventSchemaVersion,
			&event.ContentCapture,
			&event.Data,
		); err != nil {
			return page, err
		}
		page.Events = append(page.Events, event)
	}
	return page, rows.Err()
}

func projectAgentEvent(
	ctx context.Context,
	transaction pgx.Tx,
	runID string,
	event agent.Event,
) error {
	switch event.Type {
	case "context.used":
		var usage struct {
			PackageID string `json:"package_id"`
			Purpose   string `json:"purpose"`
			Items     []struct {
				ItemID     string `json:"item_id"`
				RevisionID string `json:"revision_id"`
				Type       string `json:"type"`
				Domain     string `json:"domain"`
			} `json:"items"`
		}
		if json.Unmarshal(event.Data, &usage) != nil || usage.PackageID == "" || len(usage.Items) > 50 {
			return nil
		}
		_, err := transaction.Exec(ctx, `UPDATE app_core.messages m SET metadata=jsonb_set(COALESCE(m.metadata,'{}'::jsonb),'{context_usage}',($2::jsonb || jsonb_build_object('run_id',$1::text)),true) FROM app_core.agent_runs r WHERE r.id=$1 AND m.id=r.assistant_message_id`, runID, event.Data)
		return err
	case "confirmation.required":
		confirmation, valid := conversation.ParseSkillConfirmation(event.Data)
		if !valid {
			return nil
		}
		confirmationJSON, err := json.Marshal(confirmation)
		if err != nil {
			return err
		}
		_, err = transaction.Exec(ctx, `
			UPDATE app_core.messages m
			SET metadata = jsonb_set(
				COALESCE(m.metadata, '{}'::jsonb),
				'{skill_confirmation}',
				$2::jsonb,
				true
			)
			FROM app_core.agent_runs r
			WHERE r.id = $1
				AND m.id = r.assistant_message_id
		`, runID, string(confirmationJSON))
		return err
	case "citation.created":
		citation, valid := conversation.ParseCitation(event.Data)
		if !valid {
			return nil
		}
		citationJSON, err := json.Marshal(citation)
		if err != nil {
			return err
		}
		_, err = transaction.Exec(ctx, `
			UPDATE app_core.messages m
			SET metadata = jsonb_set(
				COALESCE(m.metadata, '{}'::jsonb),
				'{citations}',
				(
					CASE
						WHEN jsonb_typeof(m.metadata->'citations') = 'array'
							THEN m.metadata->'citations'
						ELSE '[]'::jsonb
					END
				) || jsonb_build_array($2::jsonb),
				true
			)
			FROM app_core.agent_runs r
			WHERE r.id = $1
				AND m.id = r.assistant_message_id
				AND NOT EXISTS (
					SELECT 1
					FROM jsonb_array_elements(
						CASE
							WHEN jsonb_typeof(m.metadata->'citations') = 'array'
								THEN m.metadata->'citations'
							ELSE '[]'::jsonb
						END
					) existing
					WHERE existing->>'citation_id' = $3
				)
		`, runID, string(citationJSON), citation.CitationID)
		return err
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
	if status == string(agent.StatusCancelled) {
		return "stopped"
	}
	if status == string(agent.StatusTimedOut) {
		return "failed"
	}
	return status
}

func newPostgresID() string {
	return auth.NewID()
}
