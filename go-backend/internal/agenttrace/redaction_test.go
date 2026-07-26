package agenttrace

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestShouldPersist(t *testing.T) {
	t.Parallel()
	if ShouldPersist("answer.delta") || ShouldPersist("progress") {
		t.Fatal("transport-only events must not be persisted")
	}
	if !ShouldPersist("tool.completed") || !ShouldPersist("run.completed") {
		t.Fatal("durable execution events must be persisted")
	}
}

func TestSanitize(t *testing.T) {
	t.Parallel()
	raw := json.RawMessage(`{
		"api_key":"live-secret",
		"nested":{"Authorization":"Bearer credential"},
		"message":"safe",
		"input_tokens":12,
		"error":"Bearer abc.def postgres://user:password@db/agent https://example.test/?api_key=hide-me",
		"long":"` + strings.Repeat("好", 520) + `"
	}`)
	clean := string(Sanitize(raw))
	if strings.Contains(clean, "live-secret") ||
		strings.Contains(clean, "credential") ||
		strings.Contains(clean, "abc.def") ||
		strings.Contains(clean, "password@") ||
		strings.Contains(clean, "hide-me") {
		t.Fatalf("sensitive value leaked: %s", clean)
	}
	if !strings.Contains(clean, `"message":"safe"`) {
		t.Fatalf("safe metadata was lost: %s", clean)
	}
	if !strings.Contains(clean, `"input_tokens":12`) {
		t.Fatalf("token usage was incorrectly redacted: %s", clean)
	}
	if strings.Count(clean, "好") != maxStoredStringRunes {
		t.Fatalf("long string was not bounded: %s", clean)
	}
}
