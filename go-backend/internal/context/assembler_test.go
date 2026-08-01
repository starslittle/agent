package contextpackage

import (
	"testing"
	"time"
)

func TestAssembleFiltersAndEnforcesBudgets(t *testing.T) {
	now := time.Now().UTC()
	requirements := Requirements{ExecutionMode: "direct", Purpose: "conversation", NeedsPersonalContext: true, AllowedTypes: []string{"confirmed_fact"}, AllowedDomains: []string{"career"}, ItemBudget: 1, CharacterBudget: 4}
	items := []Candidate{
		{Item: Item{ItemID: "new", RevisionID: "r2", Type: "confirmed_fact", Domain: "career", Content: "abcdef", UpdatedAt: now}, ConfirmedByUser: true},
		{Item: Item{ItemID: "old", RevisionID: "r1", Type: "confirmed_fact", Domain: "career", Content: "older", UpdatedAt: now.Add(-time.Hour)}, ConfirmedByUser: true},
		{Item: Item{ItemID: "wrong", RevisionID: "r3", Type: "ai_analysis", Domain: "career", Content: "hidden", UpdatedAt: now.Add(time.Hour)}, ConfirmedByUser: true},
	}
	got, err := Assemble("p", "run", requirements, items)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Items) != 1 || got.Items[0].ItemID != "new" || got.Items[0].Content != "abcd" {
		t.Fatalf("unexpected package: %#v", got)
	}
}

func TestAssembleNoContextDoesNotLeakCandidates(t *testing.T) {
	requirements := Requirements{ExecutionMode: "direct", Purpose: "conversation", NeedsPersonalContext: false}
	got, err := Assemble("p", "run", requirements, []Candidate{{Item: Item{Content: "secret"}, ConfirmedByUser: true}})
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Items) != 0 {
		t.Fatalf("unexpected items: %#v", got.Items)
	}
}
