package postgres

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func (s *Store) ReconcileUnmanagedRuns(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
		WITH stale AS (
			UPDATE app_core.agent_runs
			SET status = 'failed',
				error_code = 'generation_interrupted',
				error_detail =
					'Unmanaged generation did not finish before service restart',
				completed_at = NOW()
			WHERE status IN ('queued', 'running', 'cancel_requested')
				AND COALESCE(
					metadata->>'run_supervisor_managed',
					'false'
				) <> 'true'
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

func (s *Store) ClaimRun(
	ctx context.Context,
	runID string,
	ownerID string,
	leaseExpiresAt time.Time,
) (conversation.ClaimedRun, bool, error) {
	return s.claimRun(ctx, runID, ownerID, leaseExpiresAt)
}

func (s *Store) ClaimNextRun(
	ctx context.Context,
	ownerID string,
	leaseExpiresAt time.Time,
) (conversation.ClaimedRun, bool, error) {
	return s.claimRun(ctx, "", ownerID, leaseExpiresAt)
}

func (s *Store) claimRun(
	ctx context.Context,
	runID string,
	ownerID string,
	leaseExpiresAt time.Time,
) (conversation.ClaimedRun, bool, error) {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return conversation.ClaimedRun{}, false, err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	var (
		claimedID      string
		previousStatus string
	)
	err = transaction.QueryRow(ctx, `
		SELECT r.id::text, r.status
		FROM app_core.agent_runs r
		WHERE r.protocol_version = 1
			AND r.metadata->>'run_supervisor_managed' = 'true'
			AND r.status IN ('queued', 'running', 'cancel_requested')
			AND ($1 = '' OR r.id = $1::uuid)
			AND COALESCE(
				(metadata->>'supervisor_lease_expires_at')::timestamptz,
				'-infinity'::timestamptz
			) <= NOW()
		ORDER BY r.started_at, r.id
		FOR UPDATE SKIP LOCKED
		LIMIT 1
	`, runID).Scan(&claimedID, &previousStatus)
	if errors.Is(err, pgx.ErrNoRows) {
		return conversation.ClaimedRun{}, false, nil
	}
	if err != nil {
		return conversation.ClaimedRun{}, false, err
	}

	var leaseEpoch int64
	err = transaction.QueryRow(ctx, `
		UPDATE app_core.agent_runs
		SET status = CASE
				WHEN status = 'queued' THEN 'running'
				ELSE status
			END,
			metadata = metadata || jsonb_build_object(
				'supervisor_owner_id', $2::text,
				'supervisor_lease_epoch',
					COALESCE(
						(metadata->>'supervisor_lease_epoch')::bigint,
						0
					) + 1,
				'supervisor_lease_expires_at', $3::timestamptz
			)
		WHERE id = $1
		RETURNING
			(metadata->>'supervisor_lease_epoch')::bigint
	`, claimedID, ownerID, leaseExpiresAt).Scan(&leaseEpoch)
	if err != nil {
		return conversation.ClaimedRun{}, false, err
	}

	claimed, err := loadClaimedRun(ctx, transaction, claimedID)
	if err != nil {
		return conversation.ClaimedRun{}, false, err
	}
	claimed.PreviousStatus = previousStatus
	claimed.Lease = conversation.RunLease{
		OwnerID:   ownerID,
		Epoch:     leaseEpoch,
		ExpiresAt: leaseExpiresAt,
	}
	if err := transaction.Commit(ctx); err != nil {
		return conversation.ClaimedRun{}, false, err
	}
	return claimed, true, nil
}

func loadClaimedRun(
	ctx context.Context,
	transaction pgx.Tx,
	runID string,
) (conversation.ClaimedRun, error) {
	var result conversation.ClaimedRun
	err := transaction.QueryRow(ctx, `
		SELECT
			c.id::text,
			c.user_id::text,
			c.title,
			c.agent_name,
			c.status,
			c.last_message_at,
			c.created_at,
			c.updated_at,
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
			r.resolved_skills,
			r.primary_skill,
			r.selection_source,
			r.context_package_id::text,
			r.metadata,
			r.status,
			r.protocol_version,
			r.last_sequence
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE r.id = $1
	`, runID).Scan(
		&result.Conversation.ID,
		&result.Conversation.UserID,
		&result.Conversation.Title,
		&result.Conversation.AgentName,
		&result.Conversation.Status,
		&result.Conversation.LastMessageAt,
		&result.Conversation.CreatedAt,
		&result.Conversation.UpdatedAt,
		&result.Run.ID,
		&result.Run.ExecutionID,
		&result.Run.IdempotencyKey,
		&result.Run.ConversationID,
		&result.Run.UserMessageID,
		&result.Run.AssistantMessageID,
		&result.Run.RequestID,
		&result.Run.AgentName,
		&result.Run.ModelID,
		&result.Run.RequestedSkill,
		&result.Run.ResolvedSkills,
		&result.Run.PrimarySkill,
		&result.Run.SelectionSource,
		&result.Run.ContextPackageID,
		&result.Run.Metadata,
		&result.Run.Status,
		&result.Run.ProtocolVersion,
		&result.Run.LastSequence,
	)
	if err != nil {
		return conversation.ClaimedRun{}, err
	}
	result.UserID = result.Conversation.UserID
	if err := transaction.QueryRow(ctx, `
		SELECT
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
		FROM app_core.messages
		WHERE id = $1
	`, result.Run.UserMessageID).Scan(
		messageScanTargets(&result.UserMessage)...,
	); err != nil {
		return conversation.ClaimedRun{}, err
	}
	if err := transaction.QueryRow(ctx, `
		SELECT
			id::text, conversation_id::text, client_message_id::text,
			role, content, status, sequence_id, metadata,
			created_at, updated_at, completed_at
		FROM app_core.messages
		WHERE id = $1
	`, result.Run.AssistantMessageID).Scan(
		messageScanTargets(&result.Assistant)...,
	); err != nil {
		return conversation.ClaimedRun{}, err
	}
	return result, nil
}

func (s *Store) RenewRunLease(
	ctx context.Context,
	runID string,
	lease conversation.RunLease,
	leaseExpiresAt time.Time,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET metadata = jsonb_set(
			metadata,
			'{supervisor_lease_expires_at}',
			to_jsonb($4::timestamptz),
			true
		)
		WHERE id = $1
			AND status IN ('running', 'cancel_requested')
			AND metadata->>'supervisor_owner_id' = $2
			AND (metadata->>'supervisor_lease_epoch')::bigint = $3
			AND (metadata->>'supervisor_lease_expires_at')::timestamptz > NOW()
	`, runID, lease.OwnerID, lease.Epoch, leaseExpiresAt)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrRunLeaseLost
	}
	return nil
}

func (s *Store) ReleaseRunLease(
	ctx context.Context,
	runID string,
	lease conversation.RunLease,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET metadata = jsonb_set(
			metadata,
			'{supervisor_lease_expires_at}',
			to_jsonb(NOW()),
			true
		)
		WHERE id = $1
			AND metadata->>'supervisor_owner_id' = $2
			AND (metadata->>'supervisor_lease_epoch')::bigint = $3
	`, runID, lease.OwnerID, lease.Epoch)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrRunLeaseLost
	}
	return nil
}

func (s *Store) CheckpointGenerationOwned(
	ctx context.Context,
	userID string,
	runID string,
	assistantMessageID string,
	content string,
	sequence int64,
	lease conversation.RunLease,
) error {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = transaction.Rollback(ctx) }()
	command, err := transaction.Exec(ctx, `
		UPDATE app_core.messages m
		SET content = $5, updated_at = NOW()
		FROM app_core.agent_runs r
		JOIN app_core.conversations c ON c.id = r.conversation_id
		WHERE m.id = $1
			AND r.id = $2
			AND r.assistant_message_id = m.id
			AND c.user_id = $3
			AND r.metadata->>'supervisor_owner_id' = $4
			AND (r.metadata->>'supervisor_lease_epoch')::bigint = $6
			AND (r.metadata->>'supervisor_lease_expires_at')::timestamptz > NOW()
			AND m.status = 'streaming'
	`, assistantMessageID, runID, userID, lease.OwnerID, content, lease.Epoch)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrRunLeaseLost
	}
	command, err = transaction.Exec(ctx, `
		UPDATE app_core.agent_runs
		SET last_sequence = GREATEST(last_sequence, $4)
		WHERE id = $1
			AND metadata->>'supervisor_owner_id' = $2
			AND (metadata->>'supervisor_lease_epoch')::bigint = $3
	`, runID, lease.OwnerID, lease.Epoch, sequence)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrRunLeaseLost
	}
	return transaction.Commit(ctx)
}

func (s *Store) AdvanceRunSequenceOwned(
	ctx context.Context,
	userID string,
	runID string,
	sequence int64,
	lease conversation.RunLease,
) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE app_core.agent_runs r
		SET last_sequence = GREATEST(last_sequence, $4)
		FROM app_core.conversations c
		WHERE r.id = $1
			AND c.id = r.conversation_id
			AND c.user_id = $2
			AND r.metadata->>'supervisor_owner_id' = $3
			AND (r.metadata->>'supervisor_lease_epoch')::bigint = $5
			AND (r.metadata->>'supervisor_lease_expires_at')::timestamptz > NOW()
	`, runID, userID, lease.OwnerID, sequence, lease.Epoch)
	if err != nil {
		return err
	}
	if command.RowsAffected() == 0 {
		return conversation.ErrRunLeaseLost
	}
	return nil
}
