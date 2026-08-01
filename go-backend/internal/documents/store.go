package documents

import (
	"context"
	"errors"
)

var (
	ErrNotFound            = errors.New("space entry not found")
	ErrInvalidInput        = errors.New("invalid space input")
	ErrNameConflict        = errors.New("space entry name conflicts with a sibling")
	ErrVersionConflict     = errors.New("space entry version conflict")
	ErrFolderNotEmpty      = errors.New("folder is not empty")
	ErrLimitExceeded       = errors.New("space limit exceeded")
	ErrIdempotencyConflict = errors.New("document import idempotency conflict")
)

type Store interface {
	CountEntries(context.Context, string) (int, error)
	FolderDepth(context.Context, string, *string) (int, error)
	CreateFolder(context.Context, CreateEntryParams) (Folder, error)
	ListEntries(context.Context, ListParams) ([]Entry, error)
	FindFolder(context.Context, string, string) (Folder, error)
	FolderBreadcrumbs(context.Context, string, string) ([]Folder, error)
	MoveEntry(context.Context, MoveEntryParams) (Entry, error)
	DeleteFolder(context.Context, string, string, int64) error
	CreateDocument(context.Context, CreateDocumentParams) (Document, error)
	FindDocument(context.Context, string, string) (Document, error)
	UpdateDocument(context.Context, UpdateDocumentParams) (Document, error)
	DeleteDocument(context.Context, string, string, int64) error
	ListDocumentRevisions(context.Context, string, string, int) ([]Revision, error)
	TouchEntry(context.Context, string, string) error
	PreviewMarkdownImport(context.Context, string, ImportManifest) ([]ImportItemResult, error)
	ImportMarkdownBatch(context.Context, ImportBatchParams) (ImportResult, error)
}
