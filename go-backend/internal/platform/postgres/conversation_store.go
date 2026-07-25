package postgres

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
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
					AND r.status IN ('queued', 'running')
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
					AND r.status IN ('queued', 'running')
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
			request_id, agent_name, status
		)
		VALUES ($1, $2, $3, $4, $5, $6, 'running')
	`, runID, params.ConversationID, userMessageID, assistantMessageID, params.RequestID, agentName)
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
		ConversationID:     params.ConversationID,
		UserMessageID:      userMessageID,
		AssistantMessageID: assistantMessageID,
		RequestID:          params.RequestID,
		AgentName:          agentName,
		Status:             "running",
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
		params.Status,
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
		SET status = $2,
			error_code = NULLIF($3, ''),
			error_detail = NULLIF($4, ''),
			first_token_at = COALESCE(first_token_at, $5),
			completed_at = $6
		WHERE id = $1 AND status IN ('queued', 'running')
	`,
		params.RunID,
		params.Status,
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

func (s *Store) InterruptStaleGenerations(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
		WITH stale AS (
			UPDATE app_core.agent_runs
			SET status = 'failed',
				error_code = 'generation_interrupted',
				error_detail = 'Generation did not finish before the service restarted',
				completed_at = NOW()
			WHERE status IN ('queued', 'running')
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

func newPostgresID() string {
	return auth.NewID()
}
