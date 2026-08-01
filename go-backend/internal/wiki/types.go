package wiki

import "time"

const (
	TypeConfirmedFact = "confirmed_fact"
	TypeCurrentState  = "current_state"
	TypePersonalRule  = "personal_rule"
	TypeAIAnalysis    = "ai_analysis"

	StatusCandidate = "candidate"
	StatusConfirmed = "confirmed"
	StatusRejected  = "rejected"
	StatusOutdated  = "outdated"
	StatusForgotten = "forgotten"

	ActorUser   = "user"
	ActorSystem = "system"
	ActorAgent  = "agent"

	SourceUserStated        = "user_stated"
	SourceUserConfirmed     = "user_confirmed"
	SourceAIInferred        = "ai_inferred"
	SourceDocumentExtracted = "document_extracted"
	SourceToolDerived       = "tool_derived"
	SourceFortuneNarrative  = "fortune_narrative"
	SourceReviewDerived     = "review_derived"
)

type Item struct {
	ID                    string     `json:"id"`
	Type                  string     `json:"type"`
	Domain                string     `json:"domain"`
	Status                string     `json:"status"`
	StatusBeforeForgotten *string    `json:"status_before_forgotten,omitempty"`
	CurrentRevisionID     string     `json:"current_revision_id"`
	Content               string     `json:"content"`
	RevisionNumber        int64      `json:"revision_number"`
	ConfirmedByUser       bool       `json:"confirmed_by_user"`
	EffectiveAt           *time.Time `json:"effective_at,omitempty"`
	Version               int64      `json:"version"`
	CreatedAt             time.Time  `json:"created_at"`
	UpdatedAt             time.Time  `json:"updated_at"`
}

type Revision struct {
	ID                 string    `json:"id"`
	ItemID             string    `json:"item_id"`
	Number             int64     `json:"revision_number"`
	Content            string    `json:"content"`
	CreatedBy          string    `json:"created_by"`
	ReplacesRevisionID *string   `json:"replaces_revision_id,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
}

type Source struct {
	ID                 string    `json:"id"`
	ItemID             string    `json:"item_id"`
	RevisionID         string    `json:"revision_id"`
	Type               string    `json:"type"`
	Reference          *string   `json:"reference,omitempty"`
	Detail             *string   `json:"detail,omitempty"`
	DocumentID         *string   `json:"document_id,omitempty"`
	DocumentRevisionID *string   `json:"document_revision_id,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
}

type ItemDetail struct {
	Item     Item     `json:"item"`
	Revision Revision `json:"revision"`
	Sources  []Source `json:"sources"`
}

type ListParams struct {
	UserID           string
	Statuses         []string
	Types            []string
	Domain           string
	Query            string
	DocumentID       *string
	IncludeForgotten bool
	Limit            int
	Offset           int
}

type SourceInput struct {
	ID                 string
	Type               string
	Reference          *string
	Detail             *string
	DocumentID         *string
	DocumentRevisionID *string
}

type CreateItemParams struct {
	ID              string
	RevisionID      string
	UserID          string
	Type            string
	Domain          string
	Status          string
	Content         string
	ConfirmedByUser bool
	EffectiveAt     *time.Time
	CreatedBy       string
	Source          SourceInput
	CreatedAt       time.Time
}

type UpdateItemParams struct {
	ItemID          string
	RevisionID      string
	UserID          string
	ExpectedVersion int64
	Content         string
	CreatedBy       string
	Source          SourceInput
	EffectiveAt     *time.Time
	UpdatedAt       time.Time
}

type ChangeStatusParams struct {
	UserID          string
	ItemID          string
	ExpectedVersion int64
	Status          string
	UpdatedAt       time.Time
}
