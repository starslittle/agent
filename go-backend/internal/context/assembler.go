package contextpackage

import (
	"sort"
	"strings"
	"unicode/utf8"
)

func Assemble(id, runID string, requirements Requirements, candidates []Candidate) (Package, error) {
	if err := requirements.Validate(); err != nil {
		return Package{}, err
	}
	result := Package{
		PackageID: id, RunID: runID, Purpose: requirements.Purpose,
		Items: []Item{}, Policy: Policy{AllowMemoryProposals: false},
		Requirements: requirements,
	}
	if !requirements.NeedsPersonalContext {
		return result, nil
	}
	types := set(requirements.AllowedTypes)
	domains := set(requirements.AllowedDomains)
	sort.SliceStable(candidates, func(i, j int) bool {
		if candidates[i].UpdatedAt.Equal(candidates[j].UpdatedAt) {
			return candidates[i].ItemID < candidates[j].ItemID
		}
		return candidates[i].UpdatedAt.After(candidates[j].UpdatedAt)
	})
	remaining := requirements.CharacterBudget
	for _, candidate := range candidates {
		if len(result.Items) >= requirements.ItemBudget || remaining <= 0 ||
			!candidate.ConfirmedByUser || !types[candidate.Type] ||
			(len(domains) > 0 && !domains[candidate.Domain]) {
			continue
		}
		content := strings.TrimSpace(candidate.Content)
		if content == "" {
			continue
		}
		runes := []rune(content)
		if len(runes) > remaining {
			runes = runes[:remaining]
		}
		candidate.Item.Content = string(runes)
		remaining -= utf8.RuneCountInString(candidate.Item.Content)
		result.Items = append(result.Items, candidate.Item)
	}
	return result, nil
}

func set(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			result[value] = true
		}
	}
	return result
}
