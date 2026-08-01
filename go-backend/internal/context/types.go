package contextpackage

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidRequirements = errors.New("invalid context requirements")
	ErrPackageConflict     = errors.New("context package conflicts with sealed run")
)

type Requirements struct {
	ExecutionMode        string   `json:"execution_mode"`
	PrimarySkill         *string  `json:"primary_skill"`
	Purpose              string   `json:"purpose"`
	NeedsPersonalContext bool     `json:"needs_personal_context"`
	AllowedTypes         []string `json:"allowed_types"`
	AllowedDomains       []string `json:"allowed_domains"`
	ItemBudget           int      `json:"item_budget"`
	CharacterBudget      int      `json:"character_budget"`
}

func (r Requirements) Validate() error {
	if strings.TrimSpace(r.ExecutionMode) == "" || strings.TrimSpace(r.Purpose) == "" ||
		r.ItemBudget < 0 || r.ItemBudget > 50 || r.CharacterBudget < 0 || r.CharacterBudget > 50000 {
		return ErrInvalidRequirements
	}
	if !r.NeedsPersonalContext && (r.ItemBudget != 0 || r.CharacterBudget != 0) {
		return ErrInvalidRequirements
	}
	return nil
}

type Policy struct {
	AllowMemoryProposals bool `json:"allow_memory_proposals"`
}

type Source struct {
	Type      string  `json:"type"`
	Reference *string `json:"reference,omitempty"`
	Detail    *string `json:"detail,omitempty"`
}

type Item struct {
	ItemID     string    `json:"item_id"`
	RevisionID string    `json:"revision_id"`
	Type       string    `json:"type"`
	Domain     string    `json:"domain"`
	Content    string    `json:"content"`
	Source     Source    `json:"source"`
	UpdatedAt  time.Time `json:"updated_at"`
}

type Package struct {
	PackageID    string       `json:"package_id"`
	RunID        string       `json:"run_id,omitempty"`
	Purpose      string       `json:"purpose"`
	Items        []Item       `json:"items"`
	Policy       Policy       `json:"policy"`
	Requirements Requirements `json:"requirements"`
	CreatedAt    time.Time    `json:"created_at,omitempty"`
}

type Candidate struct {
	Item
	ConfirmedByUser bool
}

type Usage struct {
	PackageID string      `json:"package_id"`
	RunID     string      `json:"run_id"`
	Purpose   string      `json:"purpose"`
	Items     []UsageItem `json:"items"`
}

type UsageItem struct {
	ItemID     *string    `json:"item_id,omitempty"`
	RevisionID *string    `json:"revision_id,omitempty"`
	Type       string     `json:"type"`
	Domain     string     `json:"domain"`
	Source     Source     `json:"source"`
	UpdatedAt  time.Time  `json:"updated_at"`
	RedactedAt *time.Time `json:"redacted_at,omitempty"`
}
