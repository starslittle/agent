package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/documents"
)

func (s *Store) PreviewMarkdownImport(ctx context.Context, userID string, manifest documents.ImportManifest) ([]documents.ImportItemResult, error) {
	items := []documents.ImportItemResult{}
	parentID := manifest.TargetFolderID
	if manifest.RootName != nil {
		id, kind, found, err := s.findImportEntry(ctx, userID, parentID, *manifest.RootName)
		if err != nil {
			return nil, err
		}
		if !found {
			return items, nil
		}
		if kind != documents.KindFolder {
			for _, entry := range manifest.Entries {
				if entry.Kind == "file" {
					items = append(items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportConflict, Reason: "导入根目录与现有文档同名"})
				}
			}
			return items, nil
		}
		parentID = &id
	}
	for _, entry := range manifest.Entries {
		if entry.Kind != "file" {
			continue
		}
		parts := strings.Split(entry.RelativePath, "/")
		current := parentID
		missingPath := false
		conflictPath := false
		for _, folderName := range parts[:len(parts)-1] {
			id, kind, found, err := s.findImportEntry(ctx, userID, current, folderName)
			if err != nil {
				return nil, err
			}
			if !found {
				missingPath = true
				break
			}
			if kind != documents.KindFolder {
				items = append(items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportConflict, Reason: "路径中存在同名文档"})
				conflictPath = true
				break
			}
			current = &id
		}
		if missingPath || conflictPath {
			continue
		}
		id, kind, found, err := s.findImportEntry(ctx, userID, current, parts[len(parts)-1])
		if err != nil {
			return nil, err
		}
		if !found {
			continue
		}
		status, reason := documents.ImportConflict, "同路径内容不同，未覆盖"
		if kind == documents.KindDocument {
			var hash string
			if err := s.pool.QueryRow(ctx, `SELECT r.content_hash FROM app_core.markdown_documents d JOIN app_core.markdown_document_revisions r ON r.id=d.current_revision_id WHERE d.user_id=$1 AND d.id=$2`, userID, id).Scan(&hash); err != nil {
				return nil, mapDocumentError(err)
			}
			if hash == entry.ContentHash {
				status, reason = documents.ImportSkippedDuplicate, "内容相同，将跳过"
			}
		}
		items = append(items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: status, Reason: reason, EntryID: &id})
	}
	return items, nil
}

func (s *Store) findImportEntry(ctx context.Context, userID string, parentID *string, name string) (string, string, bool, error) {
	var id, kind string
	err := s.pool.QueryRow(ctx, `SELECT id::text,kind FROM app_core.space_entries WHERE user_id=$1 AND parent_id IS NOT DISTINCT FROM $2::uuid AND name_key=$3`, userID, parentID, strings.ToLower(name)).Scan(&id, &kind)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", "", false, nil
	}
	return id, kind, err == nil, err
}

func (s *Store) ImportMarkdownBatch(ctx context.Context, params documents.ImportBatchParams) (documents.ImportResult, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return documents.ImportResult{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var existingHash string
	var existingJSON []byte
	err = tx.QueryRow(ctx, `SELECT manifest_hash,result FROM app_core.document_import_batches WHERE user_id=$1 AND idempotency_key=$2 FOR UPDATE`, params.UserID, params.IdempotencyKey).Scan(&existingHash, &existingJSON)
	if err == nil {
		if existingHash != params.ManifestHash {
			return documents.ImportResult{}, documents.ErrIdempotencyConflict
		}
		var result documents.ImportResult
		if json.Unmarshal(existingJSON, &result) != nil {
			return documents.ImportResult{}, errors.New("invalid stored import result")
		}
		result.Replayed = true
		return result, tx.Commit(ctx)
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return documents.ImportResult{}, err
	}
	if params.Manifest.TargetFolderID != nil {
		if err := tx.QueryRow(ctx, `SELECT 1 FROM app_core.space_entries WHERE user_id=$1 AND id=$2 AND kind='folder' FOR UPDATE`, params.UserID, *params.Manifest.TargetFolderID).Scan(new(int)); err != nil {
			return documents.ImportResult{}, mapDocumentError(err)
		}
	}
	result := documents.ImportResult{BatchID: params.Manifest.BatchID, Items: []documents.ImportItemResult{}}
	parentID := params.Manifest.TargetFolderID
	if params.Manifest.RootName != nil {
		rootID, status, err := ensureImportFolder(ctx, tx, params.UserID, parentID, *params.Manifest.RootName, params.CreatedAt)
		if err != nil {
			return documents.ImportResult{}, err
		}
		if status == documents.ImportConflict {
			for _, entry := range params.Manifest.Entries {
				switch entry.Kind {
				case "file":
					result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportConflict, Reason: "导入根目录与现有文档同名"})
					result.Conflicts++
				case "unsupported":
					result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportUnsupported, Reason: "仅支持 Markdown"})
					result.Unsupported++
				}
			}
			if err := persistImportResult(ctx, tx, params, result); err != nil {
				return documents.ImportResult{}, err
			}
			return result, tx.Commit(ctx)
		}
		parentID = &rootID
		result.RootFolderID = &rootID
	}
	entries := append([]documents.ImportEntry(nil), params.Manifest.Entries...)
	sort.SliceStable(entries, func(i, j int) bool {
		di, dj := strings.Count(entries[i].RelativePath, "/"), strings.Count(entries[j].RelativePath, "/")
		if di == dj {
			return entries[i].RelativePath < entries[j].RelativePath
		}
		return di < dj
	})
	for _, entry := range entries {
		if entry.Kind == "unsupported" {
			result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportUnsupported, Reason: "仅支持 Markdown"})
			result.Unsupported++
			continue
		}
		if entry.Kind != "file" {
			continue
		}
		parts := strings.Split(entry.RelativePath, "/")
		current := parentID
		for _, folderName := range parts[:len(parts)-1] {
			folderID, status, folderErr := ensureImportFolder(ctx, tx, params.UserID, current, folderName, params.CreatedAt)
			if folderErr != nil {
				return documents.ImportResult{}, folderErr
			}
			if status == documents.ImportConflict {
				result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportConflict, Reason: "路径中存在同名文档"})
				result.Conflicts++
				current = nil
				break
			}
			current = &folderID
		}
		if current == nil {
			continue
		}
		name := parts[len(parts)-1]
		nameKey := strings.ToLower(name)
		var existingID, kind, existingHash string
		err := tx.QueryRow(ctx, `SELECT e.id::text,e.kind,COALESCE(r.content_hash,'') FROM app_core.space_entries e LEFT JOIN app_core.markdown_documents d ON d.id=e.id AND d.user_id=e.user_id LEFT JOIN app_core.markdown_document_revisions r ON r.id=d.current_revision_id WHERE e.user_id=$1 AND e.parent_id=$2 AND e.name_key=$3`, params.UserID, *current, nameKey).Scan(&existingID, &kind, &existingHash)
		if err == nil {
			status := documents.ImportConflict
			reason := "同路径内容不同，未覆盖"
			if kind == documents.KindDocument && existingHash == entry.ContentHash {
				status = documents.ImportSkippedDuplicate
				reason = "内容相同，已跳过"
				result.Duplicates++
			} else {
				result.Conflicts++
			}
			result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: status, Reason: reason, EntryID: &existingID})
			continue
		}
		if !errors.Is(err, pgx.ErrNoRows) {
			return documents.ImportResult{}, err
		}
		documentID, revisionID := auth.NewID(), auth.NewID()
		if _, err := tx.Exec(ctx, `INSERT INTO app_core.space_entries(id,user_id,parent_id,kind,name,name_key,created_at,updated_at) VALUES($1,$2,$3,'document',$4,$5,$6,$6)`, documentID, params.UserID, *current, name, nameKey, params.CreatedAt); err != nil {
			return documents.ImportResult{}, mapDocumentError(err)
		}
		if _, err := tx.Exec(ctx, `INSERT INTO app_core.markdown_documents(id,user_id,extraction_status) VALUES($1,$2,'not_requested')`, documentID, params.UserID); err != nil {
			return documents.ImportResult{}, mapDocumentError(err)
		}
		original := entry.RelativePath
		if _, err := tx.Exec(ctx, `INSERT INTO app_core.markdown_document_revisions(id,document_id,user_id,revision_number,content,content_hash,size_bytes,source,original_relative_path,media_type,created_by,created_at) VALUES($1,$2,$3,1,$4,$5,$6,'import',$7,'text/markdown','user',$8)`, revisionID, documentID, params.UserID, entry.Content, entry.ContentHash, entry.Size, original, params.CreatedAt); err != nil {
			return documents.ImportResult{}, mapDocumentError(err)
		}
		if _, err := tx.Exec(ctx, `UPDATE app_core.markdown_documents SET current_revision_id=$2 WHERE id=$1`, documentID, revisionID); err != nil {
			return documents.ImportResult{}, err
		}
		result.Items = append(result.Items, documents.ImportItemResult{RelativePath: entry.RelativePath, Status: documents.ImportAdded, EntryID: &documentID})
		result.Added++
	}
	if err := persistImportResult(ctx, tx, params, result); err != nil {
		return documents.ImportResult{}, mapDocumentError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return documents.ImportResult{}, err
	}
	return result, nil
}

func persistImportResult(ctx context.Context, tx pgx.Tx, params documents.ImportBatchParams, result documents.ImportResult) error {
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `INSERT INTO app_core.document_import_batches(id,user_id,idempotency_key,target_folder_id,root_name,manifest_hash,status,result,created_at) VALUES($1,$2,$3,$4,$5,$6,'completed',$7,$8)`, params.Manifest.BatchID, params.UserID, params.IdempotencyKey, params.Manifest.TargetFolderID, params.Manifest.RootName, params.ManifestHash, resultJSON, params.CreatedAt)
	return mapDocumentError(err)
}

func ensureImportFolder(ctx context.Context, tx pgx.Tx, userID string, parentID *string, name string, createdAt time.Time) (string, string, error) {
	nameKey := strings.ToLower(name)
	var id, kind string
	err := tx.QueryRow(ctx, `SELECT id::text,kind FROM app_core.space_entries WHERE user_id=$1 AND parent_id IS NOT DISTINCT FROM $2::uuid AND name_key=$3`, userID, parentID, nameKey).Scan(&id, &kind)
	if err == nil {
		if kind != documents.KindFolder {
			return id, documents.ImportConflict, nil
		}
		return id, "existing", nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return "", "", err
	}
	id = auth.NewID()
	if _, err := tx.Exec(ctx, `INSERT INTO app_core.space_entries(id,user_id,parent_id,kind,name,name_key,created_at,updated_at) VALUES($1,$2,$3,'folder',$4,$5,$6,$6)`, id, userID, parentID, name, nameKey, createdAt); err != nil {
		return "", "", mapDocumentError(err)
	}
	return id, documents.ImportAdded, nil
}
