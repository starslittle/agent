package conversation

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

func TestResolveTerminalStatus(t *testing.T) {
	tests := []struct {
		name      string
		current   string
		requested string
		want      string
	}{
		{
			name:      "normal completion",
			current:   string(agent.StatusRunning),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCompleted),
		},
		{
			name:      "cancellation wins completion race",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCancelled),
		},
		{
			name:      "explicit cancellation stays cancelled",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusCancelled),
			want:      string(agent.StatusCancelled),
		},
		{
			name:      "failure remains observable after cancellation request",
			current:   string(agent.StatusCancelRequested),
			requested: string(agent.StatusFailed),
			want:      string(agent.StatusFailed),
		},
		{
			name:      "terminal status is irreversible",
			current:   string(agent.StatusCancelled),
			requested: string(agent.StatusCompleted),
			want:      string(agent.StatusCancelled),
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := ResolveTerminalStatus(test.current, test.requested); got != test.want {
				t.Fatalf(
					"ResolveTerminalStatus(%q, %q) = %q, want %q",
					test.current,
					test.requested,
					got,
					test.want,
				)
			}
		})
	}
}

func TestParseCitationValidatesAndBoundsBrowserData(t *testing.T) {
	t.Parallel()

	raw := json.RawMessage(`{
		"citation_id":"source-1",
		"title":" Source title ",
		"url":"https://example.com/report?q=verified",
		"snippet":"` + strings.Repeat("证", 600) + `",
		"source_type":"web",
		"artifact_id":"research_evidence:abc",
		"sequence":1
	}`)
	citation, ok := ParseCitation(raw)
	if !ok {
		t.Fatal("ParseCitation() rejected valid citation")
	}
	if citation.Title != "Source title" || len([]rune(citation.Snippet)) != 500 {
		t.Fatalf("unexpected normalized citation: %#v", citation)
	}

	invalid := []json.RawMessage{
		json.RawMessage(`{}`),
		json.RawMessage(`{"citation_id":"x","title":"x","url":"javascript:alert(1)","source_type":"web","artifact_id":"a","sequence":1}`),
		json.RawMessage(`{"citation_id":"x","title":"x","url":"https://user:pass@example.com","source_type":"web","artifact_id":"a","sequence":1}`),
		json.RawMessage(`{"citation_id":"x","title":"x","url":"https://example.com","source_type":"unknown","artifact_id":"a","sequence":1}`),
		json.RawMessage(`{"citation_id":"x","title":"x","url":"https://example.com","source_type":"web","artifact_id":"a","sequence":0}`),
	}
	for _, item := range invalid {
		if got, accepted := ParseCitation(item); accepted {
			t.Fatalf("ParseCitation(%s) = %#v, want rejected", item, got)
		}
	}
}

func TestParseSkillConfirmationRejectsUnsafeData(t *testing.T) {
	t.Parallel()

	confirmation, ok := ParseSkillConfirmation(json.RawMessage(`{
		"suggested_skill":"fortune",
		"confidence":0.94,
		"reason_code":"automatic_confirmation_required",
		"prompt":"must not be projected"
	}`))
	if !ok || confirmation.SuggestedSkill != "fortune" ||
		confirmation.Confidence != 0.94 {
		t.Fatalf("ParseSkillConfirmation() = (%#v, %t)", confirmation, ok)
	}

	invalid := []json.RawMessage{
		json.RawMessage(`{}`),
		json.RawMessage(`{"suggested_skill":"decision","confidence":0.9,"reason_code":"automatic_confirmation_required"}`),
		json.RawMessage(`{"suggested_skill":"fortune","confidence":1.1,"reason_code":"automatic_confirmation_required"}`),
		json.RawMessage(`{"suggested_skill":"fortune","confidence":0.9,"reason_code":"other"}`),
	}
	for _, item := range invalid {
		if got, accepted := ParseSkillConfirmation(item); accepted {
			t.Fatalf("ParseSkillConfirmation(%s) = %#v, want rejected", item, got)
		}
	}
}
