package skills

import (
	"errors"
	"testing"
)

func TestValidateAndProjectFiltersProductPolicyAndOrdersCatalog(t *testing.T) {
	valid := func(id string) Skill {
		return Skill{ID: id, Version: 1, Title: id, Description: "description", Command: "/" + id, PublicPurpose: "purpose", ConfirmationSummary: "confirmation", Available: true, Effective: true}
	}
	catalog, err := ValidateAndProject(Catalog{Items: []Skill{valid("fortune"), valid("future_skill"), valid("research")}})
	if err != nil {
		t.Fatal(err)
	}
	if len(catalog.Items) != 2 || catalog.Items[0].ID != "research" || catalog.Items[1].ID != "fortune" {
		t.Fatalf("catalog=%#v", catalog)
	}
}

func TestValidateAndProjectFailsClosedOnMalformedPublicCopy(t *testing.T) {
	_, err := ValidateAndProject(Catalog{Items: []Skill{
		{
			ID: "research", Version: 1, Title: "research", Description: "description",
			Command: "/research", PublicPurpose: "purpose", ConfirmationSummary: "confirmation",
			Available: true, Effective: true,
			PublicCapabilities: []Capability{{Label: "", Description: "hidden internal tool"}},
		},
	}})
	if !errors.Is(err, ErrInvalidCatalog) {
		t.Fatalf("error=%v", err)
	}
}
