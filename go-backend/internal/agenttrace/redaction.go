package agenttrace

import (
	"encoding/json"
	"regexp"
	"strings"
)

const maxStoredStringRunes = 500

var sensitiveKey = regexp.MustCompile(
	`(?i)(authorization|cookie|password|passwd|secret|api[_-]?key|` +
		`database[_-]?url|connection[_-]?string|` +
		`(^|[_-])token($|[_-])|` +
		`(access|refresh|auth|session|bearer|id)[_-]?token)`,
)
var sensitiveValues = []struct {
	pattern     *regexp.Regexp
	replacement string
}{
	{regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+`), "Bearer [redacted]"},
	{regexp.MustCompile(`(?i)\bsk-[A-Za-z0-9_-]{8,}\b`), "[redacted-api-key]"},
	{
		regexp.MustCompile(`(?i)\b([a-z][a-z0-9+.-]*://[^:/\s]+):[^@\s]+@`),
		"${1}:[redacted]@",
	},
	{
		regexp.MustCompile(`(?i)([?&](api[_-]?key|token|secret|password)=)[^&\s]+`),
		"${1}[redacted]",
	},
}

// ShouldPersist separates durable execution facts from high-volume transport events.
func ShouldPersist(eventType string) bool {
	switch eventType {
	case "answer.delta", "progress":
		return false
	default:
		return true
	}
}

// Sanitize is the gateway's final defensive boundary before event data is stored.
func Sanitize(raw json.RawMessage) json.RawMessage {
	if len(raw) == 0 {
		return json.RawMessage(`{}`)
	}
	var value any
	if err := json.Unmarshal(raw, &value); err != nil {
		return json.RawMessage(`{"redaction_error":"invalid_json"}`)
	}
	clean := sanitizeValue(value, 0)
	encoded, err := json.Marshal(clean)
	if err != nil {
		return json.RawMessage(`{"redaction_error":"encode_failed"}`)
	}
	return encoded
}

func sanitizeValue(value any, depth int) any {
	if depth > 5 {
		return "[depth-limited]"
	}
	switch item := value.(type) {
	case map[string]any:
		clean := make(map[string]any, len(item))
		for key, child := range item {
			if sensitiveKey.MatchString(key) {
				clean[key] = "[redacted]"
				continue
			}
			clean[key] = sanitizeValue(child, depth+1)
		}
		return clean
	case []any:
		limit := len(item)
		if limit > 100 {
			limit = 100
		}
		clean := make([]any, 0, limit)
		for _, child := range item[:limit] {
			clean = append(clean, sanitizeValue(child, depth+1))
		}
		return clean
	case string:
		for _, rule := range sensitiveValues {
			item = rule.pattern.ReplaceAllString(item, rule.replacement)
		}
		runes := []rune(item)
		if len(runes) <= maxStoredStringRunes {
			return item
		}
		return string(runes[:maxStoredStringRunes]) + "…"
	default:
		return value
	}
}

func CaptureLevel(level string) string {
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "off", "sampled":
		return strings.ToLower(strings.TrimSpace(level))
	default:
		return "hashed"
	}
}
