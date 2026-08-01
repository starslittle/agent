package proposals

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/auth"
)

type Service struct {
	store Store
	now   func() time.Time
}

func NewService(store Store) *Service { return &Service{store: store, now: time.Now} }

func (s *Service) Create(ctx context.Context, params CreateParams) (Proposal, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.Domain = strings.ToLower(strings.TrimSpace(params.Domain))
	params.ProposedContent = strings.TrimSpace(params.ProposedContent)
	params.ID = strings.TrimSpace(params.ID)
	params.TargetItemID = cleanPointer(params.TargetItemID)
	params.TargetRevisionID = cleanPointer(params.TargetRevisionID)
	params.DocumentID = cleanPointer(params.DocumentID)
	params.DocumentRevisionID = cleanPointer(params.DocumentRevisionID)
	params.SourceReference = cleanPointer(params.SourceReference)
	params.SourceDetail = cleanPointer(params.SourceDetail)
	if params.ID == "" {
		params.ID = auth.NewID()
	}
	params.CreatedAt = s.now().UTC()
	if params.CreatedBy != "agent" && params.CreatedBy != "system" ||
		params.UserID == "" || !validItemType(params.ItemType) || params.Domain == "" || utf8.RuneCountInString(params.Domain) > 80 ||
		!validContent(params.ProposedContent) || !validSource(params.SourceType, params.DocumentID, params.DocumentRevisionID) ||
		!validOptionalText(params.SourceReference, 2000) || !validOptionalText(params.SourceDetail, 8000) ||
		(params.TargetItemID == nil) != (params.TargetRevisionID == nil) {
		return Proposal{}, ErrInvalidInput
	}
	proposal, err := s.store.CreateWikiProposal(ctx, params)
	if errors.Is(err, ErrAlreadyExists) {
		existing, findErr := s.store.FindWikiProposal(ctx, params.UserID, params.ID)
		if findErr == nil && sameProposal(existing, params) {
			return existing, nil
		}
	}
	return proposal, err
}

func (s *Service) Get(ctx context.Context, userID, proposalID string) (Proposal, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(proposalID) == "" {
		return Proposal{}, ErrInvalidInput
	}
	return s.store.FindWikiProposal(ctx, userID, proposalID)
}

func (s *Service) List(ctx context.Context, params ListParams) ([]Proposal, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.DocumentID = cleanPointer(params.DocumentID)
	if params.UserID == "" || params.Offset < 0 {
		return nil, ErrInvalidInput
	}
	for _, status := range params.Statuses {
		if !validStatus(status) {
			return nil, ErrInvalidInput
		}
	}
	if params.Limit <= 0 {
		params.Limit = 50
	}
	if params.Limit > 200 {
		params.Limit = 200
	}
	return s.store.ListWikiProposals(ctx, params)
}

func (s *Service) Resolve(ctx context.Context, userID, proposalID, action string, finalContent *string, idempotencyKey string) (Resolution, error) {
	userID, proposalID, action = strings.TrimSpace(userID), strings.TrimSpace(proposalID), strings.TrimSpace(action)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if userID == "" || proposalID == "" || idempotencyKey == "" || utf8.RuneCountInString(idempotencyKey) > 200 || !validAction(action) {
		return Resolution{}, ErrInvalidInput
	}
	if action == ActionAccept {
		if finalContent != nil {
			content := strings.TrimSpace(*finalContent)
			if !validContent(content) {
				return Resolution{}, ErrInvalidInput
			}
			finalContent = &content
		}
	} else if finalContent != nil {
		return Resolution{}, ErrInvalidInput
	}
	encoded, _ := json.Marshal(struct {
		ProposalID string  `json:"proposal_id"`
		Action     string  `json:"action"`
		Content    *string `json:"content"`
	}{proposalID, action, finalContent})
	sum := sha256.Sum256(encoded)
	return s.store.ResolveWikiProposal(ctx, ResolveParams{
		UserID: userID, ProposalID: proposalID, Action: action, FinalContent: finalContent,
		IdempotencyKey: idempotencyKey, RequestHash: hex.EncodeToString(sum[:]), ActionID: auth.NewID(), ItemID: auth.NewID(), RevisionID: auth.NewID(),
		SourceID: auth.NewID(), ConfirmationID: auth.NewID(), ResolvedAt: s.now().UTC(),
	})
}

func validAction(value string) bool {
	return value == ActionAccept || value == ActionReject || value == ActionDefer
}
func validStatus(value string) bool {
	return value == StatusPending || value == StatusAccepted || value == StatusRejected || value == StatusDeferred || value == StatusSuperseded
}
func validItemType(value string) bool {
	return value == "confirmed_fact" || value == "current_state" || value == "personal_rule" || value == "ai_analysis"
}
func validContent(value string) bool {
	return value != "" && utf8.ValidString(value) && utf8.RuneCountInString(value) <= 20000
}
func validSource(sourceType string, documentID, revisionID *string) bool {
	switch sourceType {
	case "user_stated", "user_confirmed", "ai_inferred", "document_extracted", "tool_derived", "fortune_narrative", "review_derived":
	default:
		return false
	}
	if (documentID == nil) != (revisionID == nil) {
		return false
	}
	return sourceType != "document_extracted" || documentID != nil
}
func cleanPointer(value *string) *string {
	if value == nil {
		return nil
	}
	clean := strings.TrimSpace(*value)
	if clean == "" {
		return nil
	}
	return &clean
}
func sameProposal(proposal Proposal, params CreateParams) bool {
	return proposal.ItemType == params.ItemType && proposal.Domain == params.Domain && proposal.ProposedContent == params.ProposedContent &&
		proposal.SourceType == params.SourceType && pointersEqual(proposal.TargetItemID, params.TargetItemID) &&
		pointersEqual(proposal.TargetRevisionID, params.TargetRevisionID) && pointersEqual(proposal.DocumentID, params.DocumentID) &&
		pointersEqual(proposal.DocumentRevisionID, params.DocumentRevisionID) && pointersEqual(proposal.SourceReference, params.SourceReference) &&
		pointersEqual(proposal.SourceDetail, params.SourceDetail) && proposal.CreatedBy == params.CreatedBy
}
func pointersEqual(left, right *string) bool {
	return left == nil && right == nil || left != nil && right != nil && *left == *right
}

func validOptionalText(value *string, maxRunes int) bool {
	return value == nil || utf8.ValidString(*value) && utf8.RuneCountInString(*value) <= maxRunes
}
