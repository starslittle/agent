package postgres

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/documents"
)

func TestPersonalSpaceDocumentLifecycleIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()

	store, err := Open(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	userID := createPersonalSpaceTestUser(t, ctx, store, "documents")
	otherUserID := createPersonalSpaceTestUser(t, ctx, store, "documents-other")
	service := documents.NewService(store, documents.Limits{
		MaxDepth: 8, MaxNameRunes: 40, MaxPathRunes: 160,
		MaxDocumentBytes: 4096, MaxEntries: 100,
	})

	root, err := service.CreateFolder(ctx, userID, nil, "求职")
	if err != nil {
		t.Fatalf("CreateFolder(root) error = %v", err)
	}
	rootID := root.ID
	interviews, err := service.CreateFolder(ctx, userID, &rootID, "面试复盘")
	if err != nil {
		t.Fatalf("CreateFolder(child) error = %v", err)
	}
	interviewsID := interviews.ID
	company, err := service.CreateFolder(ctx, userID, &interviewsID, "公司研究")
	if err != nil {
		t.Fatalf("CreateFolder(grandchild) error = %v", err)
	}
	if _, err := service.CreateFolder(ctx, userID, nil, "  求职  "); !errors.Is(err, documents.ErrNameConflict) {
		t.Fatalf("normalized sibling conflict error = %v", err)
	}
	if _, err := service.CreateFolder(ctx, otherUserID, &rootID, "越权目录"); !errors.Is(err, documents.ErrNotFound) {
		t.Fatalf("cross-user parent error = %v, want not found", err)
	}

	crumbs, err := service.Breadcrumbs(ctx, userID, company.ID)
	if err != nil {
		t.Fatalf("Breadcrumbs() error = %v", err)
	}
	if len(crumbs) != 3 || crumbs[0].Name != "求职" || crumbs[2].Name != "公司研究" {
		t.Fatalf("breadcrumbs = %#v", crumbs)
	}
	if _, err := service.MoveFolder(ctx, userID, root.ID, &company.ID, root.Name, root.Version); !errors.Is(err, documents.ErrInvalidInput) {
		t.Fatalf("cycle move error = %v, want invalid input", err)
	}

	originalPath := "求职/面试复盘/腾讯.md"
	document, err := service.CreateDocument(ctx, userID, interviews.ID, "腾讯.md", "# 第一版", documents.SourceImport, &originalPath)
	if err != nil {
		t.Fatalf("CreateDocument() error = %v", err)
	}
	if document.RevisionNumber != 1 || document.Source != documents.SourceImport || document.ContentHash == "" {
		t.Fatalf("created document = %#v", document)
	}
	badPath := "../逃逸.md"
	if _, err := service.CreateDocument(ctx, userID, interviews.ID, "逃逸.md", "bad", documents.SourceImport, &badPath); !errors.Is(err, documents.ErrInvalidInput) {
		t.Fatalf("unsafe path error = %v", err)
	}
	if _, err := service.CreateFolder(ctx, userID, &interviewsID, "腾讯.md"); !errors.Is(err, documents.ErrNameConflict) {
		t.Fatalf("cross-kind sibling conflict error = %v", err)
	}
	if _, err := service.Document(ctx, otherUserID, document.ID); !errors.Is(err, documents.ErrNotFound) {
		t.Fatalf("cross-user document read error = %v", err)
	}

	updated, err := service.UpdateDocument(ctx, userID, document.ID, "# 第二版\n保留历史", document.Version)
	if err != nil {
		t.Fatalf("UpdateDocument() error = %v", err)
	}
	if updated.Version != document.Version+1 || updated.RevisionNumber != 2 {
		t.Fatalf("updated document = %#v", updated)
	}
	if _, err := service.UpdateDocument(ctx, userID, document.ID, "stale", document.Version); !errors.Is(err, documents.ErrVersionConflict) {
		t.Fatalf("stale update error = %v", err)
	}
	revisions, err := service.Revisions(ctx, userID, document.ID, 10)
	if err != nil {
		t.Fatalf("Revisions() error = %v", err)
	}
	if len(revisions) != 2 || revisions[0].Number != 2 || revisions[1].Number != 1 {
		t.Fatalf("revisions = %#v", revisions)
	}
	if err := service.DeleteFolder(ctx, userID, interviews.ID, interviews.Version); !errors.Is(err, documents.ErrFolderNotEmpty) {
		t.Fatalf("non-empty folder delete error = %v", err)
	}

	moved, err := service.MoveDocument(ctx, userID, document.ID, company.ID, "腾讯终面.md", updated.Version)
	if err != nil {
		t.Fatalf("MoveDocument() error = %v", err)
	}
	if moved.ParentID == nil || *moved.ParentID != company.ID || moved.Name != "腾讯终面.md" {
		t.Fatalf("moved document = %#v", moved)
	}
	if err := service.DeleteDocument(ctx, userID, document.ID, moved.Version); err != nil {
		t.Fatalf("DeleteDocument() error = %v", err)
	}
	if _, err := service.Document(ctx, userID, document.ID); !errors.Is(err, documents.ErrNotFound) {
		t.Fatalf("deleted document read error = %v", err)
	}
	if err := service.DeleteFolder(ctx, userID, company.ID, company.Version); err != nil {
		t.Fatalf("DeleteFolder(empty) error = %v", err)
	}
}

func createPersonalSpaceTestUser(t *testing.T, ctx context.Context, store *Store, label string) string {
	t.Helper()
	userID := auth.NewID()
	_, err := store.CreateUser(ctx, auth.CreateUserParams{
		ID: userID, Email: userID + "@example.com", DisplayName: label,
		PasswordHash: "integration-test-hash",
	})
	if err != nil {
		t.Fatalf("CreateUser() error = %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = store.pool.Exec(cleanupCtx, "DELETE FROM app_core.users WHERE id=$1", userID)
	})
	return userID
}
