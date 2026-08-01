package postgres

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/documents"
)

func TestMarkdownFolderImportIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	store, err := Open(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	userID := createPersonalSpaceTestUser(t, ctx, store, "import")
	otherID := createPersonalSpaceTestUser(t, ctx, store, "import-other")
	defer func() {
		cleanup, done := context.WithTimeout(context.Background(), 5*time.Second)
		defer done()
		_, _ = store.pool.Exec(cleanup, "DELETE FROM app_core.users WHERE id=ANY($1::uuid[])", []string{userID, otherID})
	}()
	service := documents.NewService(store, documents.DefaultLimits())
	target, err := service.CreateFolder(ctx, userID, nil, "资料")
	if err != nil {
		t.Fatal(err)
	}
	hash := func(value string) string { sum := sha256.Sum256([]byte(value)); return hex.EncodeToString(sum[:]) }
	a, b := "# A\n", "# B\n"
	manifest := documents.ImportManifest{BatchID: "11111111-1111-4111-8111-111111111111", TargetFolderID: &target.ID, RootName: stringPtr("项目"), Entries: []documents.ImportEntry{{Kind: "file", RelativePath: "a.md", Size: int64(len(a)), ContentHash: hash(a), MediaType: "text/markdown", UploadField: "file_0", Content: a}, {Kind: "file", RelativePath: "nested/b.md", Size: int64(len(b)), ContentHash: hash(b), MediaType: "text/plain; charset=utf-8", UploadField: "file_1", Content: b}, {Kind: "unsupported", RelativePath: "image.png", Size: 4, ContentHash: hash("fake")}}}
	preview, err := service.PreflightImport(ctx, userID, manifest)
	if err != nil || preview.MarkdownCount != 2 || preview.Unsupported != 1 {
		t.Fatalf("preview=%#v err=%v", preview, err)
	}
	result, err := service.Import(ctx, userID, "import-key", manifest)
	if err != nil {
		t.Fatal(err)
	}
	if result.Added != 2 || result.Unsupported != 1 || result.RootFolderID == nil {
		t.Fatalf("result=%#v", result)
	}
	duplicatePreview, err := service.PreflightImport(ctx, userID, manifest)
	if err != nil || duplicatePreview.Duplicates != 2 {
		t.Fatalf("duplicate preview=%#v err=%v", duplicatePreview, err)
	}
	replayed, err := service.Import(ctx, userID, "import-key", manifest)
	if err != nil || !replayed.Replayed {
		t.Fatalf("replay=%#v err=%v", replayed, err)
	}
	rootManifest := documents.ImportManifest{BatchID: "77777777-7777-4777-8777-777777777777", RootName: stringPtr("顶层导入"), Entries: []documents.ImportEntry{{Kind: "file", RelativePath: "root.md", Size: int64(len(a)), ContentHash: hash(a), MediaType: "text/markdown", UploadField: "file_0", Content: a}}}
	rootResult, err := service.Import(ctx, userID, "root-import-key", rootManifest)
	if err != nil || rootResult.RootFolderID == nil || rootResult.Added != 1 {
		t.Fatalf("root import=%#v err=%v", rootResult, err)
	}
	rootEntries, err := service.List(ctx, userID, nil, documents.SortName, 100, 0)
	if err != nil || !containsEntry(rootEntries, *rootResult.RootFolderID) {
		t.Fatalf("root entries=%#v err=%v", rootEntries, err)
	}
	duplicate := manifest
	duplicate.BatchID = "22222222-2222-4222-8222-222222222222"
	duplicateResult, err := service.Import(ctx, userID, "import-key-2", duplicate)
	if err != nil || duplicateResult.Duplicates != 2 {
		t.Fatalf("duplicate=%#v err=%v", duplicateResult, err)
	}
	conflict := manifest
	conflict.BatchID = "33333333-3333-4333-8333-333333333333"
	conflict.Entries = append([]documents.ImportEntry(nil), manifest.Entries...)
	conflict.Entries[0].Content = "# changed\n"
	conflict.Entries[0].Size = int64(len(conflict.Entries[0].Content))
	conflict.Entries[0].ContentHash = hash(conflict.Entries[0].Content)
	conflictResult, err := service.Import(ctx, userID, "import-key-3", conflict)
	if err != nil || conflictResult.Conflicts != 1 || conflictResult.Added != 0 {
		t.Fatalf("conflict=%#v err=%v", conflictResult, err)
	}
	bad := manifest
	bad.BatchID = "44444444-4444-4444-8444-444444444444"
	bad.RootName = stringPtr("不应存在")
	bad.Entries = append([]documents.ImportEntry(nil), manifest.Entries...)
	bad.Entries[1].ContentHash = hash("wrong")
	if _, err := service.Import(ctx, userID, "import-key-4", bad); !errors.Is(err, documents.ErrInvalidInput) {
		t.Fatalf("bad import err=%v", err)
	}
	rootItems, err := service.List(ctx, userID, &target.ID, documents.SortName, 100, 0)
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range rootItems {
		if item.Name == "不应存在" {
			t.Fatal("failed batch left a root folder")
		}
	}
	cross := manifest
	cross.BatchID = "55555555-5555-4555-8555-555555555555"
	if _, err := service.PreflightImport(ctx, otherID, cross); !errors.Is(err, documents.ErrNotFound) {
		t.Fatalf("cross-user err=%v", err)
	}
}

func stringPtr(value string) *string { return &value }

func containsEntry(items []documents.Entry, id string) bool {
	for _, item := range items {
		if item.ID == id {
			return true
		}
	}
	return false
}
