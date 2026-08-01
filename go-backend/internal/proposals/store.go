package proposals

import (
	"context"
	"errors"
)

var (
	ErrNotFound            = errors.New("wiki proposal not found")
	ErrInvalidInput        = errors.New("invalid wiki proposal input")
	ErrInvalidState        = errors.New("invalid wiki proposal state transition")
	ErrVersionConflict     = errors.New("wiki proposal target revision conflict")
	ErrAlreadyExists       = errors.New("wiki proposal already exists")
	ErrIdempotencyConflict = errors.New("wiki proposal idempotency conflict")
)

type Store interface {
	CreateWikiProposal(context.Context, CreateParams) (Proposal, error)
	FindWikiProposal(context.Context, string, string) (Proposal, error)
	ListWikiProposals(context.Context, ListParams) ([]Proposal, error)
	ResolveWikiProposal(context.Context, ResolveParams) (Resolution, error)
}
