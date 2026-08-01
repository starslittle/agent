package wiki

import (
	"context"
	"errors"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/proposals"
)

type Service struct {
	store     Store
	proposals *proposals.Service
	now       func() time.Time
}

func NewService(store Store) *Service {
	return &Service{store: store, proposals: proposals.NewService(store), now: time.Now}
}

func (s *Service) CreateProposal(ctx context.Context, params proposals.CreateParams) (proposals.Proposal, error) {
	return s.proposals.Create(ctx, params)
}

func (s *Service) Proposal(ctx context.Context, userID, proposalID string) (proposals.Proposal, error) {
	return s.proposals.Get(ctx, userID, proposalID)
}

func (s *Service) Proposals(ctx context.Context, params proposals.ListParams) ([]proposals.Proposal, error) {
	return s.proposals.List(ctx, params)
}

func (s *Service) ResolveProposal(ctx context.Context, userID, proposalID, action string, content *string, idempotencyKey string) (proposals.Resolution, error) {
	return s.proposals.Resolve(ctx, userID, proposalID, action, content, idempotencyKey)
}

func (s *Service) Create(ctx context.Context, params CreateItemParams) (ItemDetail, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.Domain = strings.ToLower(strings.TrimSpace(params.Domain))
	params.Content = strings.TrimSpace(params.Content)
	if params.ID == "" {
		params.ID = auth.NewID()
	}
	if params.RevisionID == "" {
		params.RevisionID = auth.NewID()
	}
	if params.Source.ID == "" {
		params.Source.ID = auth.NewID()
	}
	if params.CreatedBy == "" {
		params.CreatedBy = ActorUser
	}
	if params.Status == "" {
		params.Status = StatusConfirmed
	}
	if params.Status == StatusConfirmed && params.CreatedBy == ActorUser {
		params.ConfirmedByUser = true
	}
	params.CreatedAt = s.now().UTC()
	if err := validateCreate(params); err != nil {
		return ItemDetail{}, err
	}
	detail, err := s.store.CreateWikiItem(ctx, params)
	if errors.Is(err, ErrAlreadyExists) {
		existing, findErr := s.store.FindWikiItem(ctx, params.UserID, params.ID)
		if findErr == nil && existing.Item.Type == params.Type && existing.Item.Domain == params.Domain && existing.Item.Status == params.Status && existing.Item.Content == params.Content {
			return existing, nil
		}
	}
	return detail, err
}

func (s *Service) List(ctx context.Context, params ListParams) ([]Item, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.Domain = strings.ToLower(strings.TrimSpace(params.Domain))
	params.Query = strings.TrimSpace(params.Query)
	if params.UserID == "" || params.Offset < 0 {
		return nil, ErrInvalidInput
	}
	for _, status := range params.Statuses {
		if !validStatus(status) {
			return nil, ErrInvalidInput
		}
	}
	for _, itemType := range params.Types {
		if !validType(itemType) {
			return nil, ErrInvalidInput
		}
	}
	if params.Limit <= 0 {
		params.Limit = 50
	}
	if params.Limit > 200 {
		params.Limit = 200
	}
	return s.store.ListWikiItems(ctx, params)
}

func (s *Service) Get(ctx context.Context, userID, itemID string) (ItemDetail, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(itemID) == "" {
		return ItemDetail{}, ErrInvalidInput
	}
	return s.store.FindWikiItem(ctx, userID, itemID)
}

func (s *Service) Update(ctx context.Context, params UpdateItemParams) (ItemDetail, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.ItemID = strings.TrimSpace(params.ItemID)
	params.Content = strings.TrimSpace(params.Content)
	if params.RevisionID == "" {
		params.RevisionID = auth.NewID()
	}
	if params.Source.ID == "" {
		params.Source.ID = auth.NewID()
	}
	if params.CreatedBy == "" {
		params.CreatedBy = ActorUser
	}
	params.UpdatedAt = s.now().UTC()
	if params.UserID == "" || params.ItemID == "" || params.ExpectedVersion <= 0 || !validContent(params.Content) || !validActor(params.CreatedBy) || !validSource(params.Source) {
		return ItemDetail{}, ErrInvalidInput
	}
	if params.CreatedBy != ActorUser {
		return ItemDetail{}, ErrInvalidState
	}
	return s.store.UpdateWikiItem(ctx, params)
}

func (s *Service) MarkOutdated(ctx context.Context, userID, itemID string, expectedVersion int64) (Item, error) {
	return s.changeStatus(ctx, userID, itemID, expectedVersion, StatusOutdated)
}

func (s *Service) Forget(ctx context.Context, userID, itemID string, expectedVersion int64) (Item, error) {
	return s.changeStatus(ctx, userID, itemID, expectedVersion, StatusForgotten)
}

func (s *Service) Restore(ctx context.Context, userID, itemID string, expectedVersion int64) (Item, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(itemID) == "" || expectedVersion <= 0 {
		return Item{}, ErrInvalidInput
	}
	return s.store.RestoreWikiItem(ctx, userID, itemID, expectedVersion, ActorUser)
}

func (s *Service) DeletePermanently(ctx context.Context, userID, itemID string, expectedVersion int64) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(itemID) == "" || expectedVersion <= 0 {
		return ErrInvalidInput
	}
	return s.store.DeleteWikiItemPermanently(ctx, userID, itemID, expectedVersion)
}

func (s *Service) Revisions(ctx context.Context, userID, itemID string, limit int) ([]Revision, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(itemID) == "" {
		return nil, ErrInvalidInput
	}
	if limit <= 0 || limit > 100 {
		limit = 100
	}
	return s.store.ListWikiItemRevisions(ctx, userID, itemID, limit)
}

func (s *Service) changeStatus(ctx context.Context, userID, itemID string, expectedVersion int64, status string) (Item, error) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(itemID) == "" || expectedVersion <= 0 {
		return Item{}, ErrInvalidInput
	}
	return s.store.ChangeWikiItemStatus(ctx, ChangeStatusParams{UserID: userID, ItemID: itemID, ExpectedVersion: expectedVersion, Status: status, UpdatedAt: s.now().UTC()})
}

func validateCreate(params CreateItemParams) error {
	if params.UserID == "" || !validType(params.Type) || params.Domain == "" || utf8.RuneCountInString(params.Domain) > 80 || !validStatus(params.Status) || !validContent(params.Content) || !validActor(params.CreatedBy) || !validSource(params.Source) {
		return ErrInvalidInput
	}
	if params.Status == StatusConfirmed && !params.ConfirmedByUser {
		return ErrInvalidState
	}
	if params.Source.Type == SourceFortuneNarrative && params.Status == StatusConfirmed {
		return ErrInvalidState
	}
	if params.Source.Type == SourceDocumentExtracted && (params.Source.DocumentID == nil || params.Source.DocumentRevisionID == nil) {
		return ErrInvalidInput
	}
	return nil
}

func validContent(value string) bool {
	return value != "" && utf8.ValidString(value) && utf8.RuneCountInString(value) <= 20000
}
func validType(value string) bool {
	switch value {
	case TypeConfirmedFact, TypeCurrentState, TypePersonalRule, TypeAIAnalysis:
		return true
	}
	return false
}
func validStatus(value string) bool {
	switch value {
	case StatusCandidate, StatusConfirmed, StatusRejected, StatusOutdated, StatusForgotten:
		return true
	}
	return false
}
func validActor(value string) bool {
	return value == ActorUser || value == ActorSystem || value == ActorAgent
}
func validSource(value SourceInput) bool {
	switch value.Type {
	case SourceUserStated, SourceUserConfirmed, SourceAIInferred, SourceDocumentExtracted, SourceToolDerived, SourceFortuneNarrative, SourceReviewDerived:
	default:
		return false
	}
	return (value.DocumentID == nil) == (value.DocumentRevisionID == nil)
}
