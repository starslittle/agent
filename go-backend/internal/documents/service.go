package documents

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"path"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"golang.org/x/text/unicode/norm"
)

type Service struct {
	store  Store
	limits Limits
	now    func() time.Time
}

func NewService(store Store, limits Limits) *Service {
	defaults := DefaultLimits()
	if limits.MaxDepth <= 0 {
		limits.MaxDepth = defaults.MaxDepth
	}
	if limits.MaxNameRunes <= 0 {
		limits.MaxNameRunes = defaults.MaxNameRunes
	}
	if limits.MaxPathRunes <= 0 {
		limits.MaxPathRunes = defaults.MaxPathRunes
	}
	if limits.MaxDocumentBytes <= 0 {
		limits.MaxDocumentBytes = defaults.MaxDocumentBytes
	}
	if limits.MaxEntries <= 0 {
		limits.MaxEntries = defaults.MaxEntries
	}
	return &Service{store: store, limits: limits, now: time.Now}
}

func (s *Service) CreateFolder(ctx context.Context, userID string, parentID *string, name string) (Folder, error) {
	return s.CreateFolderWithID(ctx, userID, parentID, name, auth.NewID())
}

func (s *Service) CreateFolderWithID(ctx context.Context, userID string, parentID *string, name, entryID string) (Folder, error) {
	name, key, err := s.validateName(name)
	if err != nil || strings.TrimSpace(userID) == "" || strings.TrimSpace(entryID) == "" {
		return Folder{}, ErrInvalidInput
	}
	if err := s.ensureCapacity(ctx, userID); err != nil {
		return Folder{}, err
	}
	depth, err := s.store.FolderDepth(ctx, userID, parentID)
	if err != nil {
		return Folder{}, err
	}
	if depth+1 > s.limits.MaxDepth {
		return Folder{}, ErrLimitExceeded
	}
	now := s.now().UTC()
	cleanParent := cleanID(parentID)
	created, err := s.store.CreateFolder(ctx, CreateEntryParams{ID: entryID, UserID: userID, ParentID: cleanParent, Name: name, NameKey: key, CreatedAt: now})
	if errors.Is(err, ErrNameConflict) {
		existing, findErr := s.store.FindFolder(ctx, userID, entryID)
		if findErr == nil && existing.Name == name && sameID(existing.ParentID, cleanParent) {
			return existing, nil
		}
	}
	return created, err
}

func (s *Service) List(ctx context.Context, userID string, parentID *string, sortBy string, limit, offset int) ([]Entry, error) {
	if strings.TrimSpace(userID) == "" || offset < 0 {
		return nil, ErrInvalidInput
	}
	if sortBy == "" {
		sortBy = SortName
	}
	if sortBy != SortName && sortBy != SortRecent {
		return nil, ErrInvalidInput
	}
	if limit <= 0 {
		limit = 100
	}
	if limit > 200 {
		limit = 200
	}
	return s.store.ListEntries(ctx, ListParams{UserID: userID, ParentID: cleanID(parentID), Sort: sortBy, Limit: limit, Offset: offset})
}

func (s *Service) Folder(ctx context.Context, userID, folderID string) (Folder, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(folderID) == "" {
		return Folder{}, ErrInvalidInput
	}
	return s.store.FindFolder(ctx, userID, folderID)
}

func (s *Service) Breadcrumbs(ctx context.Context, userID, folderID string) ([]Folder, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(folderID) == "" {
		return nil, ErrInvalidInput
	}
	return s.store.FolderBreadcrumbs(ctx, userID, folderID)
}

func (s *Service) MoveFolder(ctx context.Context, userID, folderID string, parentID *string, name string, expectedVersion int64) (Folder, error) {
	entry, err := s.moveEntry(ctx, userID, folderID, parentID, name, expectedVersion)
	if err != nil {
		return Folder{}, err
	}
	if entry.Kind != KindFolder {
		return Folder{}, ErrNotFound
	}
	return Folder{Entry: entry}, nil
}

func (s *Service) DeleteFolder(ctx context.Context, userID, folderID string, expectedVersion int64) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(folderID) == "" || expectedVersion <= 0 {
		return ErrInvalidInput
	}
	return s.store.DeleteFolder(ctx, userID, folderID, expectedVersion)
}

func (s *Service) CreateDocument(ctx context.Context, userID, folderID, name, content, source string, originalPath *string) (Document, error) {
	return s.CreateDocumentWithID(ctx, userID, folderID, name, content, source, originalPath, auth.NewID())
}

func (s *Service) CreateDocumentWithID(ctx context.Context, userID, folderID, name, content, source string, originalPath *string, documentID string) (Document, error) {
	name, key, err := s.validateName(name)
	if err != nil || strings.TrimSpace(userID) == "" || strings.TrimSpace(folderID) == "" || strings.TrimSpace(documentID) == "" {
		return Document{}, ErrInvalidInput
	}
	if err := s.validateContent(content, source, originalPath); err != nil {
		return Document{}, err
	}
	if err := s.ensureCapacity(ctx, userID); err != nil {
		return Document{}, err
	}
	parent := folderID
	depth, err := s.store.FolderDepth(ctx, userID, &parent)
	if err != nil {
		return Document{}, err
	}
	if depth+1 > s.limits.MaxDepth {
		return Document{}, ErrLimitExceeded
	}
	now := s.now().UTC()
	hash := contentHash(content)
	created, err := s.store.CreateDocument(ctx, CreateDocumentParams{
		Entry:      CreateEntryParams{ID: documentID, UserID: userID, ParentID: &parent, Name: name, NameKey: key, CreatedAt: now},
		RevisionID: auth.NewID(), Content: content, ContentHash: hash, SizeBytes: int64(len([]byte(content))), Source: source,
		OriginalRelativePath: cleanPath(originalPath), MediaType: "text/markdown", CreatedBy: CreatedByUser,
	})
	if errors.Is(err, ErrNameConflict) {
		existing, findErr := s.store.FindDocument(ctx, userID, documentID)
		if findErr == nil && existing.Name == name && existing.ContentHash == hash && sameID(existing.ParentID, &parent) {
			return existing, nil
		}
	}
	return created, err
}

func (s *Service) Document(ctx context.Context, userID, documentID string) (Document, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(documentID) == "" {
		return Document{}, ErrInvalidInput
	}
	return s.store.FindDocument(ctx, userID, documentID)
}

func (s *Service) UpdateDocument(ctx context.Context, userID, documentID, content string, expectedVersion int64) (Document, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(documentID) == "" || expectedVersion <= 0 {
		return Document{}, ErrInvalidInput
	}
	if err := s.validateContent(content, SourceManual, nil); err != nil {
		return Document{}, err
	}
	return s.store.UpdateDocument(ctx, UpdateDocumentParams{
		UserID: userID, DocumentID: documentID, ExpectedVersion: expectedVersion, RevisionID: auth.NewID(), Content: content,
		ContentHash: contentHash(content), SizeBytes: int64(len([]byte(content))), Source: SourceManual, MediaType: "text/markdown",
		CreatedBy: CreatedByUser, UpdatedAt: s.now().UTC(),
	})
}

func (s *Service) MoveDocument(ctx context.Context, userID, documentID, folderID, name string, expectedVersion int64) (Document, error) {
	parent := folderID
	entry, err := s.moveEntry(ctx, userID, documentID, &parent, name, expectedVersion)
	if err != nil {
		return Document{}, err
	}
	if entry.Kind != KindDocument {
		return Document{}, ErrNotFound
	}
	return s.store.FindDocument(ctx, userID, documentID)
}

func (s *Service) DeleteDocument(ctx context.Context, userID, documentID string, expectedVersion int64) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(documentID) == "" || expectedVersion <= 0 {
		return ErrInvalidInput
	}
	return s.store.DeleteDocument(ctx, userID, documentID, expectedVersion)
}

func (s *Service) Revisions(ctx context.Context, userID, documentID string, limit int) ([]Revision, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(documentID) == "" {
		return nil, ErrInvalidInput
	}
	if limit <= 0 || limit > 100 {
		limit = 100
	}
	return s.store.ListDocumentRevisions(ctx, userID, documentID, limit)
}

func (s *Service) Touch(ctx context.Context, userID, entryID string) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(entryID) == "" {
		return ErrInvalidInput
	}
	return s.store.TouchEntry(ctx, userID, entryID)
}

func (s *Service) moveEntry(ctx context.Context, userID, entryID string, parentID *string, name string, expectedVersion int64) (Entry, error) {
	name, key, err := s.validateName(name)
	if err != nil || strings.TrimSpace(userID) == "" || strings.TrimSpace(entryID) == "" || expectedVersion <= 0 {
		return Entry{}, ErrInvalidInput
	}
	return s.store.MoveEntry(ctx, MoveEntryParams{UserID: userID, EntryID: entryID, ParentID: cleanID(parentID), Name: name, NameKey: key, ExpectedVersion: expectedVersion, MaxDepth: s.limits.MaxDepth, MaxPathRunes: s.limits.MaxPathRunes, UpdatedAt: s.now().UTC()})
}

func (s *Service) ensureCapacity(ctx context.Context, userID string) error {
	count, err := s.store.CountEntries(ctx, userID)
	if err != nil {
		return err
	}
	if count >= s.limits.MaxEntries {
		return ErrLimitExceeded
	}
	return nil
}

func (s *Service) validateName(raw string) (string, string, error) {
	name := strings.TrimSpace(norm.NFKC.String(raw))
	if name == "" || name == "." || name == ".." || utf8.RuneCountInString(name) > s.limits.MaxNameRunes || strings.ContainsAny(name, "/\\") {
		return "", "", ErrInvalidInput
	}
	for _, value := range name {
		if unicode.IsControl(value) {
			return "", "", ErrInvalidInput
		}
	}
	return name, strings.ToLower(name), nil
}

func (s *Service) validateContent(content, source string, originalPath *string) error {
	if !utf8.ValidString(content) || int64(len([]byte(content))) > s.limits.MaxDocumentBytes {
		return ErrLimitExceeded
	}
	if source != SourceManual && source != SourceImport {
		return ErrInvalidInput
	}
	if originalPath != nil {
		value := strings.TrimSpace(*originalPath)
		clean := path.Clean(strings.ReplaceAll(value, "\\", "/"))
		if value == "" || path.IsAbs(clean) || clean == "." || clean == ".." || strings.HasPrefix(clean, "../") || strings.ContainsRune(clean, '\x00') || utf8.RuneCountInString(clean) > s.limits.MaxPathRunes {
			return ErrInvalidInput
		}
	}
	return nil
}

func cleanID(value *string) *string {
	if value == nil {
		return nil
	}
	clean := strings.TrimSpace(*value)
	if clean == "" {
		return nil
	}
	return &clean
}

func cleanPath(value *string) *string {
	if value == nil {
		return nil
	}
	clean := path.Clean(strings.ReplaceAll(strings.TrimSpace(*value), "\\", "/"))
	return &clean
}

func contentHash(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

func sameID(left, right *string) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return *left == *right
}
