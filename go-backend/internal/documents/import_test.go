package documents

import (
	"strings"
	"testing"
)

func TestNormalizeImportManifestRejectsUnsafePathsAndContent(t *testing.T) {
	service := &Service{limits: DefaultLimits()}
	targetFolderID := "folder"
	base := ImportManifest{BatchID: "11111111-1111-4111-8111-111111111111", TargetFolderID: &targetFolderID, Entries: []ImportEntry{{Kind: "file", RelativePath: "notes/a.md", Size: 1, ContentHash: strings.Repeat("0", 64)}}}
	if _, _, err := service.normalizeImportManifest(base, false); err != nil {
		t.Fatalf("valid manifest: %v", err)
	}
	for _, unsafe := range []string{"../a.md", "/a.md", "C:/a.md", "a//b.md", "a/./b.md", "a\x00.md"} {
		copy := base
		copy.Entries = append([]ImportEntry(nil), base.Entries...)
		copy.Entries[0].RelativePath = unsafe
		if _, _, err := service.normalizeImportManifest(copy, false); err == nil {
			t.Fatalf("path %q accepted", unsafe)
		}
	}
	bad := base
	bad.Entries = append([]ImportEntry(nil), base.Entries...)
	bad.Entries[0].Content = "\x01"
	bad.Entries[0].Size = 1
	if _, _, err := service.normalizeImportManifest(bad, true); err == nil {
		t.Fatal("control content accepted")
	}
}

func TestNormalizeImportManifestReportsUnsupportedFiles(t *testing.T) {
	service := &Service{limits: DefaultLimits()}
	targetFolderID := "folder"
	manifest := ImportManifest{BatchID: "11111111-1111-4111-8111-111111111111", TargetFolderID: &targetFolderID, Entries: []ImportEntry{{Kind: "unsupported", RelativePath: "image.png", Size: 4, ContentHash: strings.Repeat("0", 64)}}}
	_, preview, err := service.normalizeImportManifest(manifest, false)
	if err != nil {
		t.Fatal(err)
	}
	if preview.Unsupported != 1 || len(preview.Items) != 1 || preview.Items[0].Status != ImportUnsupported {
		t.Fatalf("preview=%#v", preview)
	}
}

func TestNormalizeImportManifestRequiresFolderForSingleRootDocument(t *testing.T) {
	service := &Service{limits: DefaultLimits()}
	manifest := ImportManifest{BatchID: "11111111-1111-4111-8111-111111111111", Entries: []ImportEntry{{Kind: "file", RelativePath: "a.md", Size: 1, ContentHash: strings.Repeat("0", 64)}}}
	if _, _, err := service.normalizeImportManifest(manifest, false); err == nil {
		t.Fatal("single root document accepted without target folder")
	}
	manifest.RootName = importStringPtr("导入文件夹")
	if _, _, err := service.normalizeImportManifest(manifest, false); err != nil {
		t.Fatalf("root folder import rejected: %v", err)
	}
}

func importStringPtr(value string) *string { return &value }
