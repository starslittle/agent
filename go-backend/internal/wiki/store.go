package wiki

import (
	"context"
	"errors"

	"github.com/starslittle/agent/go-backend/internal/proposals"
)

var (
	ErrNotFound        = errors.New("wiki item not found")
	ErrInvalidInput    = errors.New("invalid wiki input")
	ErrVersionConflict = errors.New("wiki item version conflict")
	ErrInvalidState    = errors.New("invalid wiki item state transition")
	ErrAlreadyExists   = errors.New("wiki item already exists")
	ErrDeleted         = errors.New("wiki item was permanently deleted")
)

type Store interface {
	proposals.Store
	CreateWikiItem(context.Context, CreateItemParams) (ItemDetail, error)
	ListWikiItems(context.Context, ListParams) ([]Item, error)
	FindWikiItem(context.Context, string, string) (ItemDetail, error)
	UpdateWikiItem(context.Context, UpdateItemParams) (ItemDetail, error)
	ChangeWikiItemStatus(context.Context, ChangeStatusParams) (Item, error)
	RestoreWikiItem(context.Context, string, string, int64, string) (Item, error)
	DeleteWikiItemPermanently(context.Context, string, string, int64) error
	ListWikiItemRevisions(context.Context, string, string, int) ([]Revision, error)
}
