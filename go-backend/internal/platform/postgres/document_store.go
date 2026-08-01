package postgres

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/starslittle/agent/go-backend/internal/documents"
)

func (s *Store) CountEntries(ctx context.Context, userID string) (int, error) {
	var count int
	err := s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM app_core.space_entries WHERE user_id=$1`, userID).Scan(&count)
	return count, err
}

func (s *Store) FolderDepth(ctx context.Context, userID string, folderID *string) (int, error) {
	if folderID == nil {
		return 0, nil
	}
	var depth int
	err := s.pool.QueryRow(ctx, `
		WITH RECURSIVE ancestors AS (
			SELECT id, parent_id, 1 AS depth
			FROM app_core.space_entries
			WHERE id=$2 AND user_id=$1 AND kind='folder'
			UNION ALL
			SELECT parent.id, parent.parent_id, child.depth + 1
			FROM app_core.space_entries parent
			JOIN ancestors child ON child.parent_id = parent.id
			WHERE parent.user_id=$1 AND parent.kind='folder'
		)
		SELECT COALESCE(MAX(depth), 0) FROM ancestors
	`, userID, *folderID).Scan(&depth)
	if err != nil {
		return 0, err
	}
	if depth == 0 {
		return 0, documents.ErrNotFound
	}
	return depth, nil
}

func (s *Store) CreateFolder(ctx context.Context, params documents.CreateEntryParams) (documents.Folder, error) {
	var folder documents.Folder
	err := s.pool.QueryRow(ctx, `
		INSERT INTO app_core.space_entries
			(id, user_id, parent_id, kind, name, name_key, created_at, updated_at)
		VALUES ($1, $2, $3, 'folder', $4, $5, $6, $6)
		RETURNING id::text, parent_id::text, kind, name, version,
			last_opened_at, created_at, updated_at
	`, params.ID, params.UserID, params.ParentID, params.Name, params.NameKey, params.CreatedAt).Scan(
		&folder.ID, &folder.ParentID, &folder.Kind, &folder.Name, &folder.Version,
		&folder.LastOpenedAt, &folder.CreatedAt, &folder.UpdatedAt,
	)
	return folder, mapDocumentError(err)
}

func (s *Store) ListEntries(ctx context.Context, params documents.ListParams) ([]documents.Entry, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id::text, parent_id::text, kind, name, version,
			last_opened_at, created_at, updated_at
		FROM app_core.space_entries
		WHERE user_id=$1 AND parent_id IS NOT DISTINCT FROM $2::uuid
		ORDER BY
			CASE WHEN kind='folder' THEN 0 ELSE 1 END,
			CASE WHEN $3='recent' THEN COALESCE(last_opened_at, updated_at) END DESC,
			name_key ASC,
			id ASC
		LIMIT $4 OFFSET $5
	`, params.UserID, params.ParentID, params.Sort, params.Limit, params.Offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]documents.Entry, 0)
	for rows.Next() {
		var item documents.Entry
		if err := rows.Scan(&item.ID, &item.ParentID, &item.Kind, &item.Name, &item.Version, &item.LastOpenedAt, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) FindFolder(ctx context.Context, userID, folderID string) (documents.Folder, error) {
	var folder documents.Folder
	err := s.pool.QueryRow(ctx, `
		SELECT id::text, parent_id::text, kind, name, version,
			last_opened_at, created_at, updated_at
		FROM app_core.space_entries
		WHERE user_id=$1 AND id=$2 AND kind='folder'
	`, userID, folderID).Scan(
		&folder.ID, &folder.ParentID, &folder.Kind, &folder.Name, &folder.Version,
		&folder.LastOpenedAt, &folder.CreatedAt, &folder.UpdatedAt,
	)
	return folder, mapDocumentError(err)
}

func (s *Store) FolderBreadcrumbs(ctx context.Context, userID, folderID string) ([]documents.Folder, error) {
	rows, err := s.pool.Query(ctx, `
		WITH RECURSIVE ancestors AS (
			SELECT id, parent_id, kind, name, version, last_opened_at,
				created_at, updated_at, 0 AS depth
			FROM app_core.space_entries
			WHERE id=$2 AND user_id=$1 AND kind='folder'
			UNION ALL
			SELECT parent.id, parent.parent_id, parent.kind, parent.name,
				parent.version, parent.last_opened_at, parent.created_at,
				parent.updated_at, child.depth + 1
			FROM app_core.space_entries parent
			JOIN ancestors child ON child.parent_id=parent.id
			WHERE parent.user_id=$1 AND parent.kind='folder'
		)
		SELECT id::text, parent_id::text, kind, name, version,
			last_opened_at, created_at, updated_at
		FROM ancestors ORDER BY depth DESC
	`, userID, folderID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]documents.Folder, 0)
	for rows.Next() {
		var item documents.Folder
		if err := rows.Scan(&item.ID, &item.ParentID, &item.Kind, &item.Name, &item.Version, &item.LastOpenedAt, &item.CreatedAt, &item.UpdatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return nil, documents.ErrNotFound
	}
	return items, nil
}

func (s *Store) MoveEntry(ctx context.Context, params documents.MoveEntryParams) (documents.Entry, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return documents.Entry{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var kind string
	var currentVersion int64
	if err := tx.QueryRow(ctx, `
		SELECT kind, version FROM app_core.space_entries
		WHERE id=$2 AND user_id=$1 FOR UPDATE
	`, params.UserID, params.EntryID).Scan(&kind, &currentVersion); err != nil {
		return documents.Entry{}, mapDocumentError(err)
	}
	if currentVersion != params.ExpectedVersion {
		return documents.Entry{}, documents.ErrVersionConflict
	}
	if kind == documents.KindDocument && params.ParentID == nil {
		return documents.Entry{}, documents.ErrInvalidInput
	}
	if params.ParentID != nil {
		var parentDepth int
		var parentChars int
		err := tx.QueryRow(ctx, `
			WITH RECURSIVE ancestors AS (
				SELECT id, parent_id, char_length(name) AS chars, 1 AS depth
				FROM app_core.space_entries
				WHERE id=$2 AND user_id=$1 AND kind='folder'
				UNION ALL
				SELECT parent.id, parent.parent_id,
					child.chars + 1 + char_length(parent.name), child.depth + 1
				FROM app_core.space_entries parent
				JOIN ancestors child ON child.parent_id=parent.id
				WHERE parent.user_id=$1 AND parent.kind='folder'
			)
			SELECT COALESCE(MAX(depth), 0), COALESCE(MAX(chars), 0) FROM ancestors
		`, params.UserID, *params.ParentID).Scan(&parentDepth, &parentChars)
		if err != nil {
			return documents.Entry{}, err
		}
		if parentDepth == 0 {
			return documents.Entry{}, documents.ErrNotFound
		}
		maxRelativeDepth, maxRelativeChars := 0, 0
		if kind == documents.KindFolder {
			if err := tx.QueryRow(ctx, `
				WITH RECURSIVE descendants AS (
					SELECT id, 0 AS chars, 0 AS depth
					FROM app_core.space_entries WHERE id=$2 AND user_id=$1
					UNION ALL
					SELECT child.id, parent.chars + 1 + char_length(child.name), parent.depth + 1
					FROM app_core.space_entries child
					JOIN descendants parent ON child.parent_id=parent.id
					WHERE child.user_id=$1
				)
				SELECT COALESCE(MAX(depth), 0), COALESCE(MAX(chars), 0) FROM descendants
			`, params.UserID, params.EntryID).Scan(&maxRelativeDepth, &maxRelativeChars); err != nil {
				return documents.Entry{}, err
			}
		}
		if parentDepth+1+maxRelativeDepth > params.MaxDepth || parentChars+1+len([]rune(params.Name))+maxRelativeChars > params.MaxPathRunes {
			return documents.Entry{}, documents.ErrLimitExceeded
		}
	} else if kind == documents.KindFolder {
		var maxRelativeDepth int
		var maxRelativeChars int
		if err := tx.QueryRow(ctx, `
			WITH RECURSIVE descendants AS (
				SELECT id, 0 AS chars, 0 AS depth
				FROM app_core.space_entries WHERE id=$2 AND user_id=$1
				UNION ALL
				SELECT child.id, parent.chars + 1 + char_length(child.name), parent.depth + 1
				FROM app_core.space_entries child
				JOIN descendants parent ON child.parent_id=parent.id
				WHERE child.user_id=$1
			)
			SELECT COALESCE(MAX(depth), 0), COALESCE(MAX(chars), 0) FROM descendants
		`, params.UserID, params.EntryID).Scan(&maxRelativeDepth, &maxRelativeChars); err != nil {
			return documents.Entry{}, err
		}
		if 1+maxRelativeDepth > params.MaxDepth || len([]rune(params.Name))+maxRelativeChars > params.MaxPathRunes {
			return documents.Entry{}, documents.ErrLimitExceeded
		}
	}

	var entry documents.Entry
	err = tx.QueryRow(ctx, `
		UPDATE app_core.space_entries
		SET parent_id=$3, name=$4, name_key=$5, version=version+1, updated_at=$6
		WHERE user_id=$1 AND id=$2 AND version=$7
		RETURNING id::text, parent_id::text, kind, name, version,
			last_opened_at, created_at, updated_at
	`, params.UserID, params.EntryID, params.ParentID, params.Name, params.NameKey, params.UpdatedAt, params.ExpectedVersion).Scan(
		&entry.ID, &entry.ParentID, &entry.Kind, &entry.Name, &entry.Version,
		&entry.LastOpenedAt, &entry.CreatedAt, &entry.UpdatedAt,
	)
	if err != nil {
		return documents.Entry{}, mapDocumentError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return documents.Entry{}, mapDocumentError(err)
	}
	return entry, nil
}

func (s *Store) DeleteFolder(ctx context.Context, userID, folderID string, expectedVersion int64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var version int64
	if err := tx.QueryRow(ctx, `SELECT version FROM app_core.space_entries WHERE user_id=$1 AND id=$2 AND kind='folder' FOR UPDATE`, userID, folderID).Scan(&version); err != nil {
		return mapDocumentError(err)
	}
	if version != expectedVersion {
		return documents.ErrVersionConflict
	}
	var hasChildren bool
	if err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM app_core.space_entries WHERE user_id=$1 AND parent_id=$2)`, userID, folderID).Scan(&hasChildren); err != nil {
		return err
	}
	if hasChildren {
		return documents.ErrFolderNotEmpty
	}
	if _, err := tx.Exec(ctx, `DELETE FROM app_core.space_entries WHERE user_id=$1 AND id=$2`, userID, folderID); err != nil {
		return mapDocumentError(err)
	}
	return tx.Commit(ctx)
}

func (s *Store) CreateDocument(ctx context.Context, params documents.CreateDocumentParams) (documents.Document, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return documents.Document{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.space_entries
			(id, user_id, parent_id, kind, name, name_key, created_at, updated_at)
		VALUES ($1, $2, $3, 'document', $4, $5, $6, $6)
	`, params.Entry.ID, params.Entry.UserID, params.Entry.ParentID, params.Entry.Name, params.Entry.NameKey, params.Entry.CreatedAt); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if _, err := tx.Exec(ctx, `INSERT INTO app_core.markdown_documents (id, user_id) VALUES ($1, $2)`, params.Entry.ID, params.Entry.UserID); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.markdown_document_revisions
			(id, document_id, user_id, revision_number, content, content_hash,
			 size_bytes, source, original_relative_path, media_type, created_by, created_at)
		VALUES ($1, $2, $3, 1, $4, $5, $6, $7, $8, $9, $10, $11)
	`, params.RevisionID, params.Entry.ID, params.Entry.UserID, params.Content, params.ContentHash,
		params.SizeBytes, params.Source, params.OriginalRelativePath, params.MediaType, params.CreatedBy, params.Entry.CreatedAt); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if _, err := tx.Exec(ctx, `UPDATE app_core.markdown_documents SET current_revision_id=$2 WHERE id=$1 AND user_id=$3`, params.Entry.ID, params.RevisionID, params.Entry.UserID); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	return s.FindDocument(ctx, params.Entry.UserID, params.Entry.ID)
}

func (s *Store) FindDocument(ctx context.Context, userID, documentID string) (documents.Document, error) {
	var item documents.Document
	err := s.pool.QueryRow(ctx, documentSelect+`
		WHERE entry.user_id=$1 AND entry.id=$2 AND entry.kind='document'
			AND document.deleted_at IS NULL
	`, userID, documentID).Scan(documentScanTargets(&item)...)
	return item, mapDocumentError(err)
}

func (s *Store) UpdateDocument(ctx context.Context, params documents.UpdateDocumentParams) (documents.Document, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return documents.Document{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var currentRevisionID string
	var currentVersion int64
	err = tx.QueryRow(ctx, `
		SELECT document.current_revision_id::text, entry.version
		FROM app_core.markdown_documents document
		JOIN app_core.space_entries entry ON entry.id=document.id AND entry.user_id=document.user_id
		WHERE document.user_id=$1 AND document.id=$2 AND document.deleted_at IS NULL
		FOR UPDATE OF document, entry
	`, params.UserID, params.DocumentID).Scan(&currentRevisionID, &currentVersion)
	if err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if currentVersion != params.ExpectedVersion {
		return documents.Document{}, documents.ErrVersionConflict
	}
	var nextRevision int64
	if err := tx.QueryRow(ctx, `
		SELECT COALESCE(MAX(revision_number), 0) + 1
		FROM app_core.markdown_document_revisions
		WHERE user_id=$1 AND document_id=$2
	`, params.UserID, params.DocumentID).Scan(&nextRevision); err != nil {
		return documents.Document{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.markdown_document_revisions
			(id, document_id, user_id, revision_number, content, content_hash,
			 size_bytes, source, original_relative_path, media_type, created_by, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
	`, params.RevisionID, params.DocumentID, params.UserID, nextRevision, params.Content, params.ContentHash,
		params.SizeBytes, params.Source, params.OriginalRelativePath, params.MediaType, params.CreatedBy, params.UpdatedAt); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if _, err := tx.Exec(ctx, `UPDATE app_core.markdown_documents SET current_revision_id=$3 WHERE user_id=$1 AND id=$2`, params.UserID, params.DocumentID, params.RevisionID); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	result, err := tx.Exec(ctx, `
		UPDATE app_core.space_entries SET version=version+1, updated_at=$3
		WHERE user_id=$1 AND id=$2 AND version=$4
	`, params.UserID, params.DocumentID, params.UpdatedAt, params.ExpectedVersion)
	if err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	if result.RowsAffected() != 1 {
		return documents.Document{}, documents.ErrVersionConflict
	}
	if err := tx.Commit(ctx); err != nil {
		return documents.Document{}, mapDocumentError(err)
	}
	return s.FindDocument(ctx, params.UserID, params.DocumentID)
}

func (s *Store) DeleteDocument(ctx context.Context, userID, documentID string, expectedVersion int64) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var version int64
	if err := tx.QueryRow(ctx, `SELECT version FROM app_core.space_entries WHERE user_id=$1 AND id=$2 AND kind='document' FOR UPDATE`, userID, documentID).Scan(&version); err != nil {
		return mapDocumentError(err)
	}
	if version != expectedVersion {
		return documents.ErrVersionConflict
	}
	if _, err := tx.Exec(ctx, `DELETE FROM app_core.space_entries WHERE user_id=$1 AND id=$2`, userID, documentID); err != nil {
		return mapDocumentError(err)
	}
	return tx.Commit(ctx)
}

func (s *Store) ListDocumentRevisions(ctx context.Context, userID, documentID string, limit int) ([]documents.Revision, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT revision.id::text, revision.document_id::text, revision.revision_number,
			revision.content, revision.content_hash, revision.size_bytes, revision.source,
			revision.original_relative_path, revision.media_type, revision.created_by,
			revision.created_at
		FROM app_core.markdown_document_revisions revision
		JOIN app_core.markdown_documents document
			ON document.id=revision.document_id AND document.user_id=revision.user_id
		WHERE revision.user_id=$1 AND revision.document_id=$2 AND document.deleted_at IS NULL
		ORDER BY revision.revision_number DESC LIMIT $3
	`, userID, documentID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]documents.Revision, 0)
	for rows.Next() {
		var item documents.Revision
		if err := rows.Scan(&item.ID, &item.DocumentID, &item.Number, &item.Content, &item.ContentHash, &item.SizeBytes, &item.Source, &item.OriginalPath, &item.MediaType, &item.CreatedBy, &item.CreatedAt); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return nil, documents.ErrNotFound
	}
	return items, nil
}

func (s *Store) TouchEntry(ctx context.Context, userID, entryID string) error {
	result, err := s.pool.Exec(ctx, `UPDATE app_core.space_entries SET last_opened_at=NOW() WHERE user_id=$1 AND id=$2`, userID, entryID)
	if err != nil {
		return err
	}
	if result.RowsAffected() == 0 {
		return documents.ErrNotFound
	}
	return nil
}

const documentSelect = `
	SELECT entry.id::text, entry.parent_id::text, entry.kind, entry.name,
		entry.version, entry.last_opened_at, entry.created_at, entry.updated_at,
		document.current_revision_id::text, revision.revision_number,
		revision.content, revision.content_hash, revision.size_bytes, revision.source,
		revision.original_relative_path, revision.media_type,
		document.extraction_status, revision.created_at
	FROM app_core.space_entries entry
	JOIN app_core.markdown_documents document
		ON document.id=entry.id AND document.user_id=entry.user_id
	JOIN app_core.markdown_document_revisions revision
		ON revision.id=document.current_revision_id
		AND revision.document_id=document.id
		AND revision.user_id=document.user_id
`

func documentScanTargets(item *documents.Document) []any {
	return []any{
		&item.ID, &item.ParentID, &item.Kind, &item.Name, &item.Version,
		&item.LastOpenedAt, &item.CreatedAt, &item.UpdatedAt,
		&item.CurrentRevisionID, &item.RevisionNumber, &item.Content,
		&item.ContentHash, &item.SizeBytes, &item.Source, &item.OriginalPath,
		&item.MediaType, &item.ExtractionStatus, &item.RevisionCreatedAt,
	}
}

func mapDocumentError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return documents.ErrNotFound
	}
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) {
		switch pgError.Code {
		case "23505":
			return documents.ErrNameConflict
		case "23514":
			return documents.ErrInvalidInput
		case "23503":
			return documents.ErrNotFound
		}
	}
	if strings.Contains(err.Error(), "space parent") || strings.Contains(err.Error(), "folder move") {
		return documents.ErrInvalidInput
	}
	return fmt.Errorf("document store: %w", err)
}
