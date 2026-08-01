package postgres

import (
	"context"
	"errors"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/documents"
	"github.com/starslittle/agent/go-backend/internal/proposals"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func TestWikiProposalStateMachineIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	store, err := Open(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatal(err)
	}
	userID := createPersonalSpaceTestUser(t, ctx, store, "proposal")
	otherID := createPersonalSpaceTestUser(t, ctx, store, "proposal-other")
	defer func() {
		cleanup, done := context.WithTimeout(context.Background(), 5*time.Second)
		defer done()
		_, _ = store.pool.Exec(cleanup, "DELETE FROM app_core.users WHERE id=ANY($1::uuid[])", []string{userID, otherID})
	}()

	documentService := documents.NewService(store, documents.DefaultLimits())
	folder, err := documentService.CreateFolder(ctx, userID, nil, "复盘")
	if err != nil {
		t.Fatal(err)
	}
	document, err := documentService.CreateDocument(ctx, userID, folder.ID, "一面.md", "系统设计表达需要加强", documents.SourceManual, nil)
	if err != nil {
		t.Fatal(err)
	}
	proposalService := proposals.NewService(store)
	wikiService := wiki.NewService(store)

	createProposal, err := proposalService.Create(ctx, proposals.CreateParams{
		ID: "11111111-1111-4111-8111-111111111111", UserID: userID,
		ItemType: wiki.TypeCurrentState, Domain: "career", ProposedContent: "系统设计表达较弱",
		SourceType: wiki.SourceDocumentExtracted, DocumentID: &document.ID,
		DocumentRevisionID: &document.CurrentRevisionID, CreatedBy: wiki.ActorAgent,
	})
	if err != nil {
		t.Fatal(err)
	}
	if createProposal.Status != proposals.StatusPending || createProposal.Operation != proposals.OperationCreate {
		t.Fatalf("proposal=%#v", createProposal)
	}
	if _, err := proposalService.Get(ctx, otherID, createProposal.ID); !errors.Is(err, proposals.ErrNotFound) {
		t.Fatalf("cross-user get err=%v", err)
	}
	edited := "系统设计表达需要结合真实项目加强"
	accepted, err := proposalService.Resolve(ctx, userID, createProposal.ID, proposals.ActionAccept, &edited, "accept-create")
	if err != nil {
		t.Fatal(err)
	}
	if accepted.Proposal.ProposedContent == edited || accepted.Proposal.FinalContent == nil || *accepted.Proposal.FinalContent != edited || accepted.AppliedItemID == nil {
		t.Fatalf("accepted=%#v", accepted)
	}
	createdWiki, err := wikiService.Get(ctx, userID, *accepted.AppliedItemID)
	if err != nil {
		t.Fatal(err)
	}
	if createdWiki.Item.Content != edited || !createdWiki.Item.ConfirmedByUser || len(createdWiki.Sources) != 2 {
		t.Fatalf("created wiki=%#v", createdWiki)
	}
	replay, err := proposalService.Resolve(ctx, userID, createProposal.ID, proposals.ActionAccept, &edited, "accept-create")
	if err != nil || !replay.Replayed || *replay.AppliedRevisionID != *accepted.AppliedRevisionID {
		t.Fatalf("replay=%#v err=%v", replay, err)
	}
	if _, err := proposalService.Resolve(ctx, userID, createProposal.ID, proposals.ActionReject, nil, "accept-create"); !errors.Is(err, proposals.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict err=%v", err)
	}
	if _, err := proposalService.Resolve(ctx, userID, createProposal.ID, proposals.ActionAccept, &edited, "accept-again"); !errors.Is(err, proposals.ErrInvalidState) {
		t.Fatalf("repeat accept err=%v", err)
	}

	target := createdWiki.Item
	firstUpdate, err := proposalService.Create(ctx, updateProposalParams("22222222-2222-4222-8222-222222222222", userID, target, "已开始准备系统设计"))
	if err != nil {
		t.Fatal(err)
	}
	secondUpdate, err := proposalService.Create(ctx, updateProposalParams("33333333-3333-4333-8333-333333333333", userID, target, "系统设计准备已完成"))
	if err != nil {
		t.Fatal(err)
	}
	updatedResult, err := proposalService.Resolve(ctx, userID, firstUpdate.ID, proposals.ActionAccept, nil, "accept-update")
	if err != nil {
		t.Fatal(err)
	}
	updatedWiki, err := wikiService.Get(ctx, userID, target.ID)
	if err != nil || updatedWiki.Item.RevisionNumber != 2 || updatedWiki.Item.Content != firstUpdate.ProposedContent {
		t.Fatalf("updated wiki=%#v err=%v", updatedWiki, err)
	}
	superseded, err := proposalService.Get(ctx, userID, secondUpdate.ID)
	if err != nil || superseded.Status != proposals.StatusSuperseded {
		t.Fatalf("superseded=%#v err=%v", superseded, err)
	}
	if updatedResult.AppliedItemID == nil || *updatedResult.AppliedItemID != target.ID {
		t.Fatalf("updated result=%#v", updatedResult)
	}

	stale, err := proposalService.Create(ctx, updateProposalParams("44444444-4444-4444-8444-444444444444", userID, updatedWiki.Item, "过期建议"))
	if err != nil {
		t.Fatal(err)
	}
	manual, err := wikiService.Update(ctx, wiki.UpdateItemParams{UserID: userID, ItemID: target.ID, ExpectedVersion: updatedWiki.Item.Version, Content: "用户手动更新", CreatedBy: wiki.ActorUser, Source: wiki.SourceInput{Type: wiki.SourceUserStated}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := proposalService.Resolve(ctx, userID, stale.ID, proposals.ActionAccept, nil, "stale-accept"); !errors.Is(err, proposals.ErrVersionConflict) {
		t.Fatalf("stale accept err=%v", err)
	}
	staleAfter, _ := proposalService.Get(ctx, userID, stale.ID)
	if staleAfter.Status != proposals.StatusPending {
		t.Fatalf("stale proposal mutated=%#v", staleAfter)
	}
	revisions, err := wikiService.Revisions(ctx, userID, target.ID, 10)
	if err != nil || len(revisions) != 3 || manual.Item.RevisionNumber != 3 {
		t.Fatalf("revisions=%#v manual=%#v err=%v", revisions, manual, err)
	}

	deferred, err := proposalService.Create(ctx, proposals.CreateParams{ID: "55555555-5555-4555-8555-555555555555", UserID: userID, ItemType: wiki.TypePersonalRule, Domain: "career", ProposedContent: "优先结合真实项目", SourceType: wiki.SourceAIInferred, CreatedBy: wiki.ActorAgent})
	if err != nil {
		t.Fatal(err)
	}
	deferredResult, err := proposalService.Resolve(ctx, userID, deferred.ID, proposals.ActionDefer, nil, "defer-key")
	if err != nil || deferredResult.Proposal.Status != proposals.StatusDeferred || deferredResult.AppliedItemID != nil {
		t.Fatalf("deferred=%#v err=%v", deferredResult, err)
	}
	rejectedResult, err := proposalService.Resolve(ctx, userID, deferred.ID, proposals.ActionReject, nil, "reject-key")
	if err != nil || rejectedResult.Proposal.Status != proposals.StatusRejected {
		t.Fatalf("rejected=%#v err=%v", rejectedResult, err)
	}

	fortune, err := proposalService.Create(ctx, proposals.CreateParams{ID: "66666666-6666-4666-8666-666666666666", UserID: userID, ItemType: wiki.TypeConfirmedFact, Domain: "fortune", ProposedContent: "命理解读会确定未来", SourceType: wiki.SourceFortuneNarrative, CreatedBy: wiki.ActorAgent})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := proposalService.Resolve(ctx, userID, fortune.ID, proposals.ActionAccept, nil, "fortune-key"); !errors.Is(err, proposals.ErrInvalidState) {
		t.Fatalf("fortune accept err=%v", err)
	}
	if _, err := proposalService.Resolve(ctx, otherID, fortune.ID, proposals.ActionReject, nil, "cross-key"); !errors.Is(err, proposals.ErrNotFound) {
		t.Fatalf("cross-user resolve err=%v", err)
	}
}

func TestWikiProposalConcurrentAcceptIntegration(t *testing.T) {
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
	userID := createPersonalSpaceTestUser(t, ctx, store, "proposal-race")
	defer func() { _, _ = store.pool.Exec(context.Background(), "DELETE FROM app_core.users WHERE id=$1", userID) }()
	service := proposals.NewService(store)
	proposal, err := service.Create(ctx, proposals.CreateParams{ID: "77777777-7777-4777-8777-777777777777", UserID: userID, ItemType: wiki.TypeAIAnalysis, Domain: "career", ProposedContent: "表达结构需要加强", SourceType: wiki.SourceAIInferred, CreatedBy: wiki.ActorAgent})
	if err != nil {
		t.Fatal(err)
	}
	start := make(chan struct{})
	errorsFound := make(chan error, 2)
	var wait sync.WaitGroup
	for _, key := range []string{"race-a", "race-b"} {
		wait.Add(1)
		go func(idempotencyKey string) {
			defer wait.Done()
			<-start
			_, resolveErr := service.Resolve(ctx, userID, proposal.ID, proposals.ActionAccept, nil, idempotencyKey)
			errorsFound <- resolveErr
		}(key)
	}
	close(start)
	wait.Wait()
	close(errorsFound)
	success, invalid := 0, 0
	for resolveErr := range errorsFound {
		if resolveErr == nil {
			success++
		} else if errors.Is(resolveErr, proposals.ErrInvalidState) {
			invalid++
		} else {
			t.Fatalf("unexpected concurrent error=%v", resolveErr)
		}
	}
	if success != 1 || invalid != 1 {
		t.Fatalf("success=%d invalid=%d", success, invalid)
	}

	sameKeyProposal, err := service.Create(ctx, proposals.CreateParams{ID: "99999999-9999-4999-8999-999999999999", UserID: userID, ItemType: wiki.TypePersonalRule, Domain: "career", ProposedContent: "优先使用真实经历", SourceType: wiki.SourceAIInferred, CreatedBy: wiki.ActorAgent})
	if err != nil {
		t.Fatal(err)
	}
	type outcome struct {
		result proposals.Resolution
		err    error
	}
	sameStart := make(chan struct{})
	outcomes := make(chan outcome, 2)
	for index := 0; index < 2; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-sameStart
			result, resolveErr := service.Resolve(ctx, userID, sameKeyProposal.ID, proposals.ActionAccept, nil, "same-race-key")
			outcomes <- outcome{result: result, err: resolveErr}
		}()
	}
	close(sameStart)
	wait.Wait()
	close(outcomes)
	replayed := 0
	for item := range outcomes {
		if item.err != nil {
			t.Fatalf("same-key concurrent error=%v", item.err)
		}
		if item.result.Replayed {
			replayed++
		}
	}
	if replayed != 1 {
		t.Fatalf("same-key replayed=%d", replayed)
	}
}

func updateProposalParams(id, userID string, target wiki.Item, content string) proposals.CreateParams {
	return proposals.CreateParams{ID: id, UserID: userID, TargetItemID: &target.ID, TargetRevisionID: &target.CurrentRevisionID, ItemType: target.Type, Domain: target.Domain, ProposedContent: content, SourceType: wiki.SourceAIInferred, CreatedBy: wiki.ActorAgent}
}
