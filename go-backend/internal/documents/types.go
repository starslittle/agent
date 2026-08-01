package documents

import "time"

const (
	KindFolder   = "folder"
	KindDocument = "document"

	SortName   = "name"
	SortRecent = "recent"

	SourceManual = "manual"
	SourceImport = "import"

	CreatedByUser   = "user"
	CreatedBySystem = "system"
	CreatedByAgent  = "agent"
)

type Limits struct {
	MaxDepth         int
	MaxNameRunes     int
	MaxPathRunes     int
	MaxDocumentBytes int64
	MaxEntries       int
}

func DefaultLimits() Limits {
	return Limits{
		MaxDepth:         32,
		MaxNameRunes:     120,
		MaxPathRunes:     2048,
		MaxDocumentBytes: 2 * 1024 * 1024,
		MaxEntries:       10000,
	}
}

type Entry struct {
	ID           string     `json:"id"`
	ParentID     *string    `json:"parent_id,omitempty"`
	Kind         string     `json:"kind"`
	Name         string     `json:"name"`
	Version      int64      `json:"version"`
	LastOpenedAt *time.Time `json:"last_opened_at,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
	UpdatedAt    time.Time  `json:"updated_at"`
}

type Folder struct {
	Entry
}

type Document struct {
	Entry
	CurrentRevisionID string    `json:"current_revision_id"`
	RevisionNumber    int64     `json:"revision_number"`
	Content           string    `json:"content"`
	ContentHash       string    `json:"content_hash"`
	SizeBytes         int64     `json:"size_bytes"`
	Source            string    `json:"source"`
	OriginalPath      *string   `json:"original_relative_path,omitempty"`
	MediaType         string    `json:"media_type"`
	ExtractionStatus  string    `json:"extraction_status"`
	RevisionCreatedAt time.Time `json:"revision_created_at"`
}

type Revision struct {
	ID           string    `json:"id"`
	DocumentID   string    `json:"document_id"`
	Number       int64     `json:"revision_number"`
	Content      string    `json:"content"`
	ContentHash  string    `json:"content_hash"`
	SizeBytes    int64     `json:"size_bytes"`
	Source       string    `json:"source"`
	OriginalPath *string   `json:"original_relative_path,omitempty"`
	MediaType    string    `json:"media_type"`
	CreatedBy    string    `json:"created_by"`
	CreatedAt    time.Time `json:"created_at"`
}

type ListParams struct {
	UserID   string
	ParentID *string
	Sort     string
	Limit    int
	Offset   int
}

type CreateEntryParams struct {
	ID        string
	UserID    string
	ParentID  *string
	Name      string
	NameKey   string
	CreatedAt time.Time
}

type CreateDocumentParams struct {
	Entry                CreateEntryParams
	RevisionID           string
	Content              string
	ContentHash          string
	SizeBytes            int64
	Source               string
	OriginalRelativePath *string
	MediaType            string
	CreatedBy            string
}

type UpdateDocumentParams struct {
	UserID               string
	DocumentID           string
	ExpectedVersion      int64
	RevisionID           string
	Content              string
	ContentHash          string
	SizeBytes            int64
	Source               string
	OriginalRelativePath *string
	MediaType            string
	CreatedBy            string
	UpdatedAt            time.Time
}

type MoveEntryParams struct {
	UserID          string
	EntryID         string
	ParentID        *string
	Name            string
	NameKey         string
	ExpectedVersion int64
	MaxDepth        int
	MaxPathRunes    int
	UpdatedAt       time.Time
}
