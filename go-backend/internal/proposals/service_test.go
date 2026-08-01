package proposals

import (
	"context"
	"errors"
	"testing"
)

func TestServiceRejectsUntrustedCreationAndInvalidTransitions(t *testing.T) {
	service := NewService(nil)
	_, err := service.Create(context.Background(), CreateParams{UserID: "user", ItemType: "current_state", Domain: "career", ProposedContent: "candidate", SourceType: "ai_inferred", CreatedBy: "user"})
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("user-created proposal err=%v", err)
	}
	target := "item"
	_, err = service.Create(context.Background(), CreateParams{UserID: "user", TargetItemID: &target, ItemType: "current_state", Domain: "career", ProposedContent: "candidate", SourceType: "ai_inferred", CreatedBy: "agent"})
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("partial target pair err=%v", err)
	}
	content := "not allowed"
	_, err = service.Resolve(context.Background(), "user", "proposal", ActionReject, &content, "key")
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("reject with edited content err=%v", err)
	}
	empty := "  "
	_, err = service.Resolve(context.Background(), "user", "proposal", ActionAccept, &empty, "key")
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("accept with empty content err=%v", err)
	}
}
