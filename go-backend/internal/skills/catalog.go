package skills

import (
	"errors"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"
)

var (
	ErrInvalidCatalog = errors.New("invalid public skill catalog")
	skillIDPattern    = regexp.MustCompile(`^[a-z][a-z0-9_]{0,63}$`)
	productOrder      = map[string]int{"research": 0, "fortune": 1}
)

type Capability struct {
	Label       string `json:"label"`
	Description string `json:"description"`
}

type ContextScope struct {
	Label string `json:"label"`
}

type Skill struct {
	ID                  string         `json:"id"`
	Version             int64          `json:"version"`
	Title               string         `json:"title"`
	Description         string         `json:"description"`
	Command             string         `json:"command"`
	PublicPurpose       string         `json:"public_purpose"`
	PublicCapabilities  []Capability   `json:"public_capabilities"`
	ContextScope        []ContextScope `json:"context_scope"`
	ConfirmationSummary string         `json:"confirmation_summary"`
	MayProposeUpdates   bool           `json:"may_propose_updates"`
	Available           bool           `json:"available"`
	Effective           bool           `json:"effective"`
}

type Catalog struct {
	Items []Skill `json:"items"`
}

func ValidateAndProject(catalog Catalog) (Catalog, error) {
	if len(catalog.Items) > 128 {
		return Catalog{}, ErrInvalidCatalog
	}
	seen := make(map[string]struct{}, len(catalog.Items))
	projected := make([]Skill, 0, len(catalog.Items))
	for _, skill := range catalog.Items {
		skill.ID = strings.TrimSpace(skill.ID)
		if _, allowed := productOrder[skill.ID]; !allowed {
			continue
		}
		if _, duplicate := seen[skill.ID]; duplicate || !validSkill(skill) {
			return Catalog{}, ErrInvalidCatalog
		}
		seen[skill.ID] = struct{}{}
		if skill.Available && skill.Effective {
			projected = append(projected, skill)
		}
	}
	sort.Slice(projected, func(i, j int) bool { return productOrder[projected[i].ID] < productOrder[projected[j].ID] })
	return Catalog{Items: projected}, nil
}

func validSkill(skill Skill) bool {
	if !skillIDPattern.MatchString(skill.ID) || skill.Version <= 0 || skill.Command != "/"+skill.ID ||
		!bounded(skill.Title, 1, 128) || !bounded(skill.Description, 1, 1000) ||
		!bounded(skill.PublicPurpose, 1, 1000) || !bounded(skill.ConfirmationSummary, 1, 1000) ||
		len(skill.PublicCapabilities) > 64 || len(skill.ContextScope) > 8 {
		return false
	}
	for _, capability := range skill.PublicCapabilities {
		if !bounded(capability.Label, 1, 128) || !bounded(capability.Description, 1, 500) {
			return false
		}
	}
	for _, scope := range skill.ContextScope {
		if !bounded(scope.Label, 1, 128) {
			return false
		}
	}
	return true
}

func bounded(value string, minimum, maximum int) bool {
	value = strings.TrimSpace(value)
	return utf8.ValidString(value) && utf8.RuneCountInString(value) >= minimum && utf8.RuneCountInString(value) <= maximum
}
