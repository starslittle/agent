package agent

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestStateMachine(t *testing.T) {
	if !CanTransition(StatusQueued, StatusCancelRequested) {
		t.Fatal("queued must be cancellable before running")
	}
	if !CanTransition(StatusCancelRequested, StatusCancelled) {
		t.Fatal("cancel_requested must transition to cancelled")
	}
	if CanTransition(StatusCompleted, StatusRunning) {
		t.Fatal("terminal state must not regress")
	}
}

func TestProtocolFixture(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("testdata", "agent_protocol_v1_events.json"))
	if err != nil {
		t.Fatal(err)
	}
	var events []Event
	if err := json.Unmarshal(content, &events); err != nil {
		t.Fatal(err)
	}
	for index, event := range events {
		if err := event.Validate("exec_fixture_001"); err != nil {
			t.Fatalf("event %d: %v", index, err)
		}
		expected := int64(index + 1)
		if event.Sequence != expected {
			t.Fatalf("sequence = %d, want %d", event.Sequence, expected)
		}
	}
	if got := events[1].SSEID(); got != "exec_fixture_001:2" {
		t.Fatalf("SSEID() = %q", got)
	}
}

func TestNormalizeRunSelectionSupportsNewAndLegacyContracts(t *testing.T) {
	research := "research"
	selection, err := NormalizeRunSelection("auto", &research, "")
	if err != nil {
		t.Fatal(err)
	}
	if selection.AgentName != "research" ||
		selection.RequestedSkill == nil ||
		*selection.RequestedSkill != "research" {
		t.Fatalf("explicit selection = %#v", selection)
	}

	legacy, err := NormalizeRunSelection("", nil, "fortune_agent")
	if err != nil {
		t.Fatal(err)
	}
	if legacy.ModelID != "auto" || legacy.RequestedSkill == nil ||
		*legacy.RequestedSkill != "fortune" {
		t.Fatalf("legacy selection = %#v", legacy)
	}
	internal, err := NormalizeRunSelection("auto", nil, "document_extraction")
	if err != nil || internal.AgentName != "document_extraction" || internal.RequestedSkill != nil {
		t.Fatalf("document extraction selection = %#v, err=%v", internal, err)
	}

	if _, err := NormalizeRunSelection("provider/model", nil, ""); err == nil {
		t.Fatal("arbitrary model_id must be rejected")
	}
	unknown := "decision"
	if _, err := NormalizeRunSelection("auto", &unknown, ""); err == nil {
		t.Fatal("unknown requested_skill must be rejected")
	}
}

func TestRunRequestMarshalPreservesSelectionSourceMarker(t *testing.T) {
	for _, test := range []struct {
		name      string
		agentName string
		wantAgent string
	}{
		{name: "explicit skill marker", agentName: "research", wantAgent: "research"},
		{name: "legacy agent marker", agentName: "research_agent", wantAgent: "research_agent"},
	} {
		t.Run(test.name, func(t *testing.T) {
			content, err := json.Marshal(RunRequest{
				ProtocolVersion: ProtocolVersion,
				ExecutionID:     "exec-source",
				RunID:           "run-source",
				RequestID:       "request-source",
				IdempotencyKey:  "idempotency-source",
				ConversationID:  "conversation-source",
				AgentName:       test.agentName,
				Query:           "research this",
				DeadlineMS:      1000,
			})
			if err != nil {
				t.Fatal(err)
			}
			var payload map[string]any
			if err := json.Unmarshal(content, &payload); err != nil {
				t.Fatal(err)
			}
			if payload["agent_name"] != test.wantAgent ||
				payload["requested_skill"] != "research" {
				t.Fatalf("payload = %#v", payload)
			}
		})
	}
}

func TestRunRequestMarshalProjectsNormalizedCompatibilityFields(t *testing.T) {
	content, err := json.Marshal(RunRequest{
		ProtocolVersion: ProtocolVersion,
		ExecutionID:     "exec-contract",
		RunID:           "run-contract",
		RequestID:       "request-contract",
		IdempotencyKey:  "idempotency-contract",
		ConversationID:  "conversation-contract",
		AgentName:       "research_agent",
		Query:           "research this",
		DeadlineMS:      1000,
	})
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(content, &payload); err != nil {
		t.Fatal(err)
	}
	if payload["model_id"] != "auto" || payload["requested_skill"] != "research" {
		t.Fatalf("payload = %#v", payload)
	}
	resolved, ok := payload["resolved_skills"].([]any)
	if !ok || len(resolved) != 0 {
		t.Fatalf("resolved_skills = %#v", payload["resolved_skills"])
	}
}

func TestParseSkillResolutionRejectsInconsistentProjection(t *testing.T) {
	valid := json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":"research",
		"resolved_skills":["research"],
		"primary_skill":"research",
		"selection_source":"user",
		"skill_snapshot":{"id":"research","version":1},
		"model_snapshot":{"model_id":"auto"},
		"context_package_id":null
	}`)
	resolution, err := ParseSkillResolution(valid)
	if err != nil || resolution.PrimarySkill == nil ||
		*resolution.PrimarySkill != "research" {
		t.Fatalf("resolution = %#v, error = %v", resolution, err)
	}

	invalid := json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":"research",
		"resolved_skills":[],
		"primary_skill":"research",
		"selection_source":"user",
		"model_snapshot":{"model_id":"auto"}
	}`)
	if _, err := ParseSkillResolution(invalid); err == nil {
		t.Fatal("inconsistent projection must fail")
	}
}

func TestParseSkillResolutionPreservesDirectCapability(t *testing.T) {
	resolution, err := ParseSkillResolution(json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":null,
		"resolved_skills":[],
		"primary_skill":null,
		"selection_source":"direct",
		"skill_snapshot":null,
		"model_snapshot":{"model_id":"auto"},
		"context_package_id":null,
		"direct_capability":"get_weather",
		"direct_capability_arguments":{"location":"杭州"}
	}`))
	if err != nil {
		t.Fatal(err)
	}
	if resolution.DirectCapability == nil ||
		*resolution.DirectCapability != "get_weather" ||
		resolution.DirectCapabilityArgs["location"] != "杭州" {
		t.Fatalf("resolution = %#v", resolution)
	}
}

func TestParseSkillResolutionAcceptsConfirmationOnlyProjection(t *testing.T) {
	resolution, err := ParseSkillResolution(json.RawMessage(`{
		"model_id":"auto",
		"requested_skill":null,
		"resolved_skills":[],
		"primary_skill":null,
		"selection_source":"automatic",
		"skill_snapshot":null,
		"model_snapshot":{"model_id":"auto"},
		"context_package_id":null,
		"suggested_skill":"fortune",
		"confidence":0.99,
		"requires_confirmation":true,
		"reason_code":"automatic_confirmation_required"
	}`))
	if err != nil || !resolution.RequiresConfirm ||
		resolution.SuggestedSkill == nil || *resolution.SuggestedSkill != "fortune" {
		t.Fatalf("resolution = %#v, error = %v", resolution, err)
	}
}
