package postgres

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/documents"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func TestWikiLifecycleAndDocumentIndependenceIntegration(t *testing.T) {
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

	userID := createPersonalSpaceTestUser(t, ctx, store, "wiki")
	otherUserID := createPersonalSpaceTestUser(t, ctx, store, "wiki-other")
	documentService := documents.NewService(store, documents.DefaultLimits())
	folder, err := documentService.CreateFolder(ctx, userID, nil, "现状")
	if err != nil {
		t.Fatalf("CreateFolder() error = %v", err)
	}
	document, err := documentService.CreateDocument(ctx, userID, folder.ID, "目标.md", "目标是 AI 产品", documents.SourceManual, nil)
	if err != nil {
		t.Fatalf("CreateDocument() error = %v", err)
	}

	wikiService := wiki.NewService(store)
	documentID, revisionID := document.ID, document.CurrentRevisionID
	detail, err := wikiService.Create(ctx, wiki.CreateItemParams{
		UserID: userID, Type: wiki.TypeCurrentState, Domain: "career",
		Status: wiki.StatusConfirmed, Content: "目标是寻找 AI 产品岗位",
		CreatedBy: wiki.ActorUser,
		Source: wiki.SourceInput{
			Type:       wiki.SourceDocumentExtracted,
			DocumentID: &documentID, DocumentRevisionID: &revisionID,
		},
	})
	if err != nil {
		t.Fatalf("Create(wiki item) error = %v", err)
	}
	if !detail.Item.ConfirmedByUser || len(detail.Sources) != 1 || detail.Sources[0].DocumentID == nil {
		t.Fatalf("created wiki detail = %#v", detail)
	}
	if _, err := wikiService.Get(ctx, otherUserID, detail.Item.ID); !errors.Is(err, wiki.ErrNotFound) {
		t.Fatalf("cross-user wiki read error = %v", err)
	}

	updated, err := wikiService.Update(ctx, wiki.UpdateItemParams{
		UserID: userID, ItemID: detail.Item.ID, ExpectedVersion: detail.Item.Version,
		Content: "目标是寻找可持续积累的 AI 产品岗位", CreatedBy: wiki.ActorUser,
		Source: wiki.SourceInput{Type: wiki.SourceUserStated},
	})
	if err != nil {
		t.Fatalf("Update() error = %v", err)
	}
	if updated.Item.RevisionNumber != 2 || updated.Revision.ReplacesRevisionID == nil {
		t.Fatalf("updated wiki detail = %#v", updated)
	}
	if _, err := wikiService.Update(ctx, wiki.UpdateItemParams{
		UserID: userID, ItemID: detail.Item.ID, ExpectedVersion: detail.Item.Version,
		Content: "stale", CreatedBy: wiki.ActorUser,
		Source: wiki.SourceInput{Type: wiki.SourceUserStated},
	}); !errors.Is(err, wiki.ErrVersionConflict) {
		t.Fatalf("stale wiki update error = %v", err)
	}
	revisions, err := wikiService.Revisions(ctx, userID, detail.Item.ID, 10)
	if err != nil || len(revisions) != 2 {
		t.Fatalf("Revisions() len=%d error=%v", len(revisions), err)
	}

	forgotten, err := wikiService.Forget(ctx, userID, detail.Item.ID, updated.Item.Version)
	if err != nil || forgotten.Status != wiki.StatusForgotten {
		t.Fatalf("Forget() item=%#v error=%v", forgotten, err)
	}
	listed, err := wikiService.List(ctx, wiki.ListParams{UserID: userID})
	if err != nil || len(listed) != 0 {
		t.Fatalf("default list after forget = %#v error=%v", listed, err)
	}
	restored, err := wikiService.Restore(ctx, userID, detail.Item.ID, forgotten.Version)
	if err != nil || restored.Status != wiki.StatusConfirmed {
		t.Fatalf("Restore() item=%#v error=%v", restored, err)
	}

	if err := documentService.DeleteDocument(ctx, userID, document.ID, document.Version); err != nil {
		t.Fatalf("DeleteDocument() error = %v", err)
	}
	stillPresent, err := wikiService.Get(ctx, userID, detail.Item.ID)
	if err != nil {
		t.Fatalf("wiki item after document deletion error = %v", err)
	}
	if len(stillPresent.Sources) != 1 || stillPresent.Sources[0].DocumentID != nil || stillPresent.Sources[0].DocumentRevisionID != nil {
		t.Fatalf("document source was not detached safely: %#v", stillPresent.Sources)
	}

	if err := wikiService.DeletePermanently(ctx, userID, detail.Item.ID, restored.Version); err != nil {
		t.Fatalf("DeletePermanently() error = %v", err)
	}
	if _, err := wikiService.Get(ctx, userID, detail.Item.ID); !errors.Is(err, wiki.ErrNotFound) {
		t.Fatalf("permanently deleted read error = %v", err)
	}
	if err := wikiService.DeletePermanently(ctx, userID, detail.Item.ID, restored.Version); !errors.Is(err, wiki.ErrDeleted) {
		t.Fatalf("repeated permanent delete error = %v", err)
	}
}

func TestWikiServiceRejectsSilentConfirmation(t *testing.T) {
	service := wiki.NewService(nil)
	_, err := service.Create(context.Background(), wiki.CreateItemParams{
		UserID: "user", Type: wiki.TypeAIAnalysis, Domain: "career",
		Status: wiki.StatusConfirmed, Content: "AI inferred claim",
		CreatedBy: wiki.ActorAgent,
		Source:    wiki.SourceInput{Type: wiki.SourceAIInferred},
	})
	if !errors.Is(err, wiki.ErrInvalidState) {
		t.Fatalf("agent confirmed item error = %v", err)
	}
	_, err = service.Create(context.Background(), wiki.CreateItemParams{
		UserID: "user", Type: wiki.TypeAIAnalysis, Domain: "fortune",
		Status: wiki.StatusConfirmed, Content: "fortune narrative",
		CreatedBy: wiki.ActorUser,
		Source:    wiki.SourceInput{Type: wiki.SourceFortuneNarrative},
	})
	if !errors.Is(err, wiki.ErrInvalidState) {
		t.Fatalf("fortune confirmed item error = %v", err)
	}
}
