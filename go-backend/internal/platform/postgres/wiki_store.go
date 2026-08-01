package postgres

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func (s *Store) CreateWikiItem(ctx context.Context, params wiki.CreateItemParams) (wiki.ItemDetail, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return wiki.ItemDetail{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.wiki_items
			(id, user_id, item_type, domain, status, confirmed_by_user,
			 effective_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
	`, params.ID, params.UserID, params.Type, params.Domain, params.Status,
		params.ConfirmedByUser, params.EffectiveAt, params.CreatedAt); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.wiki_item_revisions
			(id, item_id, user_id, revision_number, content, created_by, created_at)
		VALUES ($1, $2, $3, 1, $4, $5, $6)
	`, params.RevisionID, params.ID, params.UserID, params.Content, params.CreatedBy, params.CreatedAt); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if err := insertWikiSource(ctx, tx, params.UserID, params.ID, params.RevisionID, params.Source, params.CreatedAt); err != nil {
		return wiki.ItemDetail{}, err
	}
	if _, err := tx.Exec(ctx, `UPDATE app_core.wiki_items SET current_revision_id=$3 WHERE user_id=$1 AND id=$2`, params.UserID, params.ID, params.RevisionID); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	return s.FindWikiItem(ctx, params.UserID, params.ID)
}

func (s *Store) ListWikiItems(ctx context.Context, params wiki.ListParams) ([]wiki.Item, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT item.id::text, item.item_type, item.domain, item.status,
			item.status_before_forgotten, item.current_revision_id::text,
			revision.content, revision.revision_number, item.confirmed_by_user,
			item.effective_at, item.version, item.created_at, item.updated_at
		FROM app_core.wiki_items item
		JOIN app_core.wiki_item_revisions revision
			ON revision.id=item.current_revision_id
			AND revision.item_id=item.id AND revision.user_id=item.user_id
		WHERE item.user_id=$1
			AND ($2::text[] IS NULL OR item.status=ANY($2))
			AND ($3::text[] IS NULL OR item.item_type=ANY($3))
			AND ($4='' OR item.domain=$4)
			AND ($5='' OR revision.content ILIKE '%' || $5 || '%')
			AND ($6::boolean OR item.status <> 'forgotten')
			AND ($7::uuid IS NULL OR EXISTS (
				SELECT 1 FROM app_core.wiki_item_sources source
				WHERE source.item_id=item.id AND source.user_id=item.user_id
					AND source.document_id=$7
			))
		ORDER BY item.updated_at DESC, item.id DESC
		LIMIT $8 OFFSET $9
	`, params.UserID, nullableStrings(params.Statuses), nullableStrings(params.Types),
		params.Domain, params.Query, params.IncludeForgotten, params.DocumentID,
		params.Limit, params.Offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]wiki.Item, 0)
	for rows.Next() {
		var item wiki.Item
		if err := rows.Scan(wikiItemScanTargets(&item)...); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) FindWikiItem(ctx context.Context, userID, itemID string) (wiki.ItemDetail, error) {
	var detail wiki.ItemDetail
	err := s.pool.QueryRow(ctx, wikiItemSelect+` WHERE item.user_id=$1 AND item.id=$2`, userID, itemID).Scan(
		wikiItemScanTargets(&detail.Item)...,
	)
	if err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	detail.Revision = wiki.Revision{
		ID:      detail.Item.CurrentRevisionID,
		ItemID:  detail.Item.ID,
		Number:  detail.Item.RevisionNumber,
		Content: detail.Item.Content,
	}
	if err := s.pool.QueryRow(ctx, `
		SELECT created_by, replaces_revision_id::text, created_at
		FROM app_core.wiki_item_revisions
		WHERE user_id=$1 AND item_id=$2 AND id=$3
	`, userID, itemID, detail.Item.CurrentRevisionID).Scan(
		&detail.Revision.CreatedBy, &detail.Revision.ReplacesRevisionID, &detail.Revision.CreatedAt,
	); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	sources, err := s.listWikiSources(ctx, userID, itemID, detail.Item.CurrentRevisionID)
	if err != nil {
		return wiki.ItemDetail{}, err
	}
	detail.Sources = sources
	usage, err := s.ListContextUsageForItem(ctx, userID, itemID)
	if err != nil {
		return wiki.ItemDetail{}, err
	}
	detail.Usage = usage
	return detail, nil
}

func (s *Store) UpdateWikiItem(ctx context.Context, params wiki.UpdateItemParams) (wiki.ItemDetail, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return wiki.ItemDetail{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var currentRevision string
	var currentVersion int64
	var currentStatus string
	if err := tx.QueryRow(ctx, `
		SELECT current_revision_id::text, version, status
		FROM app_core.wiki_items WHERE user_id=$1 AND id=$2 FOR UPDATE
	`, params.UserID, params.ItemID).Scan(&currentRevision, &currentVersion, &currentStatus); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if currentVersion != params.ExpectedVersion {
		return wiki.ItemDetail{}, wiki.ErrVersionConflict
	}
	if currentStatus == wiki.StatusForgotten || currentStatus == wiki.StatusRejected {
		return wiki.ItemDetail{}, wiki.ErrInvalidState
	}
	var nextRevision int64
	if err := tx.QueryRow(ctx, `SELECT COALESCE(MAX(revision_number),0)+1 FROM app_core.wiki_item_revisions WHERE user_id=$1 AND item_id=$2`, params.UserID, params.ItemID).Scan(&nextRevision); err != nil {
		return wiki.ItemDetail{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.wiki_item_revisions
			(id, item_id, user_id, revision_number, content, created_by,
			 replaces_revision_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`, params.RevisionID, params.ItemID, params.UserID, nextRevision, params.Content,
		params.CreatedBy, currentRevision, params.UpdatedAt); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if err := insertWikiSource(ctx, tx, params.UserID, params.ItemID, params.RevisionID, params.Source, params.UpdatedAt); err != nil {
		return wiki.ItemDetail{}, err
	}
	result, err := tx.Exec(ctx, `
		UPDATE app_core.wiki_items
		SET current_revision_id=$3, effective_at=COALESCE($4, effective_at),
			version=version+1, updated_at=$5
		WHERE user_id=$1 AND id=$2 AND version=$6
	`, params.UserID, params.ItemID, params.RevisionID, params.EffectiveAt,
		params.UpdatedAt, params.ExpectedVersion)
	if err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	if result.RowsAffected() != 1 {
		return wiki.ItemDetail{}, wiki.ErrVersionConflict
	}
	if err := tx.Commit(ctx); err != nil {
		return wiki.ItemDetail{}, mapWikiError(err)
	}
	return s.FindWikiItem(ctx, params.UserID, params.ItemID)
}

func (s *Store) ChangeWikiItemStatus(ctx context.Context, params wiki.ChangeStatusParams) (wiki.Item, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return wiki.Item{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var currentStatus string
	var currentVersion int64
	if err := tx.QueryRow(ctx, `SELECT status, version FROM app_core.wiki_items WHERE user_id=$1 AND id=$2 FOR UPDATE`, params.UserID, params.ItemID).Scan(&currentStatus, &currentVersion); err != nil {
		return wiki.Item{}, mapWikiError(err)
	}
	if currentVersion != params.ExpectedVersion {
		return wiki.Item{}, wiki.ErrVersionConflict
	}
	var statusBefore any
	switch params.Status {
	case wiki.StatusOutdated:
		if currentStatus != wiki.StatusConfirmed && currentStatus != wiki.StatusCandidate {
			return wiki.Item{}, wiki.ErrInvalidState
		}
	case wiki.StatusForgotten:
		if currentStatus == wiki.StatusForgotten {
			return wiki.Item{}, wiki.ErrInvalidState
		}
		statusBefore = currentStatus
	default:
		return wiki.Item{}, wiki.ErrInvalidState
	}
	var item wiki.Item
	err = tx.QueryRow(ctx, `
		UPDATE app_core.wiki_items
		SET status=$3,
			status_before_forgotten=CASE WHEN $3='forgotten' THEN $4 ELSE status_before_forgotten END,
			version=version+1, updated_at=$5
		WHERE user_id=$1 AND id=$2 AND version=$6
		RETURNING id::text, item_type, domain, status, status_before_forgotten,
			current_revision_id::text, ''::text, 0::bigint, confirmed_by_user,
			effective_at, version, created_at, updated_at
	`, params.UserID, params.ItemID, params.Status, statusBefore, params.UpdatedAt, params.ExpectedVersion).Scan(wikiItemScanTargets(&item)...)
	if err != nil {
		return wiki.Item{}, mapWikiError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return wiki.Item{}, err
	}
	detail, err := s.FindWikiItem(ctx, params.UserID, params.ItemID)
	return detail.Item, err
}

func (s *Store) RestoreWikiItem(ctx context.Context, userID, itemID string, expectedVersion int64, actor string) (wiki.Item, error) {
	if actor != wiki.ActorUser {
		return wiki.Item{}, wiki.ErrInvalidState
	}
	result, err := s.pool.Exec(ctx, `
		UPDATE app_core.wiki_items
		SET status=status_before_forgotten, status_before_forgotten=NULL,
			version=version+1, updated_at=NOW()
		WHERE user_id=$1 AND id=$2 AND version=$3 AND status='forgotten'
			AND status_before_forgotten IS NOT NULL
	`, userID, itemID, expectedVersion)
	if err != nil {
		return wiki.Item{}, mapWikiError(err)
	}
	if result.RowsAffected() != 1 {
		return wiki.Item{}, classifyWikiWriteMiss(ctx, s, userID, itemID, expectedVersion)
	}
	detail, err := s.FindWikiItem(ctx, userID, itemID)
	return detail.Item, err
}

func (s *Store) DeleteWikiItemPermanently(ctx context.Context, userID, itemID string, expectedVersion int64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var version int64
	if err := tx.QueryRow(ctx, `SELECT version FROM app_core.wiki_items WHERE user_id=$1 AND id=$2 FOR UPDATE`, userID, itemID).Scan(&version); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			var exists bool
			if tombstoneErr := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM app_core.wiki_item_tombstones WHERE user_id=$1 AND item_id=$2)`, userID, itemID).Scan(&exists); tombstoneErr == nil && exists {
				return wiki.ErrDeleted
			}
		}
		return mapWikiError(err)
	}
	if version != expectedVersion {
		return wiki.ErrVersionConflict
	}
	if err := redactContextForWikiItem(ctx, tx, userID, itemID); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.wiki_item_tombstones (item_id, user_id, deleted_by_user)
		VALUES ($1, $2, $2) ON CONFLICT (item_id, user_id) DO NOTHING
	`, itemID, userID); err != nil {
		return mapWikiError(err)
	}
	if _, err := tx.Exec(ctx, `DELETE FROM app_core.wiki_items WHERE user_id=$1 AND id=$2`, userID, itemID); err != nil {
		return mapWikiError(err)
	}
	return tx.Commit(ctx)
}

func (s *Store) ListWikiItemRevisions(ctx context.Context, userID, itemID string, limit int) ([]wiki.Revision, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, item_id::text, revision_number, content, created_by,
			replaces_revision_id::text, created_at
		FROM app_core.wiki_item_revisions
		WHERE user_id=$1 AND item_id=$2
		ORDER BY revision_number DESC LIMIT $3
	`, userID, itemID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]wiki.Revision, 0)
	for rows.Next() {
		var item wiki.Revision
		if err := rows.Scan(&item.ID, &item.ItemID, &item.Number, &item.Content, &item.CreatedBy, &item.ReplacesRevisionID, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return nil, wiki.ErrNotFound
	}
	return items, nil
}

func (s *Store) listWikiSources(ctx context.Context, userID, itemID, revisionID string) ([]wiki.Source, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, item_id::text, revision_id::text, source_type,
			source_ref, source_detail, document_id::text,
			document_revision_id::text, created_at
		FROM app_core.wiki_item_sources
		WHERE user_id=$1 AND item_id=$2 AND revision_id=$3
		ORDER BY created_at, id
	`, userID, itemID, revisionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]wiki.Source, 0)
	for rows.Next() {
		var item wiki.Source
		if err := rows.Scan(&item.ID, &item.ItemID, &item.RevisionID, &item.Type, &item.Reference, &item.Detail, &item.DocumentID, &item.DocumentRevisionID, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func insertWikiSource(ctx context.Context, tx pgx.Tx, userID, itemID, revisionID string, source wiki.SourceInput, createdAt any) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO app_core.wiki_item_sources
			(id, item_id, revision_id, user_id, source_type, source_ref,
			 source_detail, document_id, document_revision_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`, source.ID, itemID, revisionID, userID, source.Type, source.Reference,
		source.Detail, source.DocumentID, source.DocumentRevisionID, createdAt)
	return mapWikiError(err)
}

const wikiItemSelect = `
	SELECT item.id::text, item.item_type, item.domain, item.status,
		item.status_before_forgotten, item.current_revision_id::text,
		revision.content, revision.revision_number, item.confirmed_by_user,
		item.effective_at, item.version, item.created_at, item.updated_at
	FROM app_core.wiki_items item
	JOIN app_core.wiki_item_revisions revision
		ON revision.id=item.current_revision_id
		AND revision.item_id=item.id AND revision.user_id=item.user_id
`

func wikiItemScanTargets(item *wiki.Item) []any {
	return []any{
		&item.ID, &item.Type, &item.Domain, &item.Status,
		&item.StatusBeforeForgotten, &item.CurrentRevisionID, &item.Content,
		&item.RevisionNumber, &item.ConfirmedByUser, &item.EffectiveAt,
		&item.Version, &item.CreatedAt, &item.UpdatedAt,
	}
}

func nullableStrings(values []string) any {
	if len(values) == 0 {
		return nil
	}
	return values
}

func classifyWikiWriteMiss(ctx context.Context, store *Store, userID, itemID string, expectedVersion int64) error {
	var version int64
	err := store.pool.QueryRow(ctx, `SELECT version FROM app_core.wiki_items WHERE user_id=$1 AND id=$2`, userID, itemID).Scan(&version)
	if errors.Is(err, pgx.ErrNoRows) {
		return wiki.ErrNotFound
	}
	if err != nil {
		return err
	}
	if version != expectedVersion {
		return wiki.ErrVersionConflict
	}
	return wiki.ErrInvalidState
}

func mapWikiError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return wiki.ErrNotFound
	}
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) {
		switch pgError.Code {
		case "23505":
			return wiki.ErrAlreadyExists
		case "23514", "22P02":
			return wiki.ErrInvalidInput
		case "23503":
			return wiki.ErrNotFound
		}
	}
	if strings.Contains(err.Error(), "wiki") {
		return fmt.Errorf("wiki store: %w", err)
	}
	return err
}
