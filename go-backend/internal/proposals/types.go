package proposals

import "time"

const (
	OperationCreate = "create"
	OperationUpdate = "update"

	StatusPending    = "pending"
	StatusAccepted   = "accepted"
	StatusRejected   = "rejected"
	StatusDeferred   = "deferred"
	StatusSuperseded = "superseded"

	ActionAccept = "accept"
	ActionReject = "reject"
	ActionDefer  = "defer"
)

type Proposal struct {
	ID                 string     `json:"id"`
	TargetItemID       *string    `json:"target_item_id,omitempty"`
	TargetRevisionID   *string    `json:"target_revision_id,omitempty"`
	Operation          string     `json:"operation"`
	ItemType           string     `json:"item_type"`
	Domain             string     `json:"domain"`
	ProposedContent    string     `json:"proposed_content"`
	SourceType         string     `json:"source_type"`
	SourceReference    *string    `json:"source_reference,omitempty"`
	SourceDetail       *string    `json:"source_detail,omitempty"`
	DocumentID         *string    `json:"document_id,omitempty"`
	DocumentRevisionID *string    `json:"document_revision_id,omitempty"`
	Status             string     `json:"status"`
	FinalContent       *string    `json:"final_content,omitempty"`
	ResolutionAction   *string    `json:"resolution_action,omitempty"`
	ResolvedByUserID   *string    `json:"resolved_by_user_id,omitempty"`
	ResolvedAt         *time.Time `json:"resolved_at,omitempty"`
	AppliedItemID      *string    `json:"applied_item_id,omitempty"`
	AppliedRevisionID  *string    `json:"applied_revision_id,omitempty"`
	CreatedBy          string     `json:"created_by"`
	Version            int64      `json:"version"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
}

type ListParams struct {
	UserID     string
	Statuses   []string
	DocumentID *string
	Limit      int
	Offset     int
}

type CreateParams struct {
	ID                 string
	UserID             string
	TargetItemID       *string
	TargetRevisionID   *string
	ItemType           string
	Domain             string
	ProposedContent    string
	SourceType         string
	SourceReference    *string
	SourceDetail       *string
	DocumentID         *string
	DocumentRevisionID *string
	CreatedBy          string
	CreatedAt          time.Time
}

type ResolveParams struct {
	UserID         string
	ProposalID     string
	Action         string
	FinalContent   *string
	IdempotencyKey string
	RequestHash    string
	ActionID       string
	ItemID         string
	RevisionID     string
	SourceID       string
	ConfirmationID string
	ResolvedAt     time.Time
}

type Resolution struct {
	Proposal          Proposal `json:"proposal"`
	AppliedItemID     *string  `json:"applied_item_id,omitempty"`
	AppliedRevisionID *string  `json:"applied_revision_id,omitempty"`
	Replayed          bool     `json:"replayed"`
}
