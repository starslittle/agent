package httpapi

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/starslittle/agent/go-backend/internal/agent"
)

func TestProjectBrowserEvent(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		eventType string
		data      string
		wantType  string
		wantKind  string
		wantState string
		wantLabel string
	}{
		{
			name:      "progress",
			eventType: "progress",
			data:      `{"stage":"research.collect","secret":"hidden"}`,
			wantType:  "activity",
			wantKind:  "progress",
			wantState: "running",
			wantLabel: "正在收集资料",
		},
		{
			name:      "route",
			eventType: "route.selected",
			data:      `{"selected_workflow":"research_v1"}`,
			wantType:  "activity",
			wantKind:  "route",
			wantState: "completed",
			wantLabel: "已选择执行路线",
		},
		{
			name:      "model started",
			eventType: "model.started",
			data:      `{"prompt":"hidden"}`,
			wantType:  "activity",
			wantKind:  "model",
			wantState: "started",
			wantLabel: "正在生成回答",
		},
		{
			name:      "model completed",
			eventType: "model.completed",
			data:      `{"duration_ms":28,"usage":{"input_tokens":999}}`,
			wantType:  "activity",
			wantKind:  "model",
			wantState: "completed",
			wantLabel: "回答生成完成",
		},
		{
			name:      "model failed",
			eventType: "model.failed",
			data:      `{"duration_ms":28,"error_code":"ProviderSecret"}`,
			wantType:  "activity",
			wantKind:  "model",
			wantState: "failed",
			wantLabel: "回答生成失败",
		},
		{
			name:      "tool started",
			eventType: "tool.started",
			data:      `{"name":"tavily_search","arguments":{"token":"secret"}}`,
			wantType:  "activity",
			wantKind:  "tool",
			wantState: "started",
			wantLabel: "正在联网检索",
		},
		{
			name:      "tool completed",
			eventType: "tool.completed",
			data:      `{"name":"tavily_search","duration_ms":834,"result":"secret"}`,
			wantType:  "activity",
			wantKind:  "tool",
			wantState: "completed",
			wantLabel: "联网检索完成",
		},
		{
			name:      "tool failed",
			eventType: "tool.failed",
			data:      `{"name":"unknown_private_tool","error_code":"secret stack"}`,
			wantType:  "activity",
			wantKind:  "tool",
			wantState: "failed",
			wantLabel: "工具执行失败",
		},
		{
			name:      "tool cancelled",
			eventType: "tool.cancelled",
			data:      `{"name":"get_lunar_chart","duration_ms":10}`,
			wantType:  "activity",
			wantKind:  "tool",
			wantState: "cancelled",
			wantLabel: "命盘计算已取消",
		},
		{
			name:      "answer",
			eventType: "answer.delta",
			data:      `{"text":"正文"}`,
			wantType:  "answer_delta",
		},
		{
			name:      "artifact",
			eventType: "artifact.created",
			data: `{
				"artifact_id":"report:abc",
				"artifact_type":"research_report",
				"content_hash":"abc123",
				"media_type":"application/json",
				"size_bytes":42,
				"content":"secret"
			}`,
			wantType: "artifact",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			payload, visible := projectBrowserEvent(agent.Event{
				Sequence: 12,
				Type:     test.eventType,
				Data:     json.RawMessage(test.data),
			})
			if !visible {
				t.Fatal("projectBrowserEvent() visible = false")
			}
			encoded, err := json.Marshal(payload)
			if err != nil {
				t.Fatalf("json.Marshal() error = %v", err)
			}
			var got map[string]any
			if err := json.Unmarshal(encoded, &got); err != nil {
				t.Fatalf("json.Unmarshal() error = %v", err)
			}
			if got["type"] != test.wantType {
				t.Fatalf("type = %#v, want %q", got["type"], test.wantType)
			}
			if got["sequence"] != float64(12) {
				t.Fatalf("sequence = %#v, want 12", got["sequence"])
			}
			if test.wantKind != "" {
				activity, ok := got["activity"].(map[string]any)
				if !ok {
					t.Fatalf("activity = %#v", got["activity"])
				}
				if activity["kind"] != test.wantKind ||
					activity["status"] != test.wantState ||
					activity["label"] != test.wantLabel {
					t.Fatalf("activity = %#v", activity)
				}
			}
			for _, forbidden := range []string{
				"secret",
				"ProviderSecret",
				"unknown_private_tool",
				`"arguments"`,
				`"result"`,
				`"error_code"`,
				`"content":`,
				`"prompt"`,
				`"usage"`,
			} {
				if strings.Contains(string(encoded), forbidden) {
					t.Fatalf("payload leaked %q: %s", forbidden, encoded)
				}
			}
		})
	}
}

func TestProjectBrowserEventRejectsMalformedOrUnknownData(t *testing.T) {
	t.Parallel()

	tests := []agent.Event{
		{Sequence: 1, Type: "unknown.event", Data: json.RawMessage(`{"text":"leak"}`)},
		{Sequence: 2, Type: "answer.delta", Data: json.RawMessage(`{`)},
		{Sequence: 3, Type: "answer.delta", Data: json.RawMessage(`{"text":""}`)},
		{
			Sequence: 4,
			Type:     "artifact.created",
			Data:     json.RawMessage(`{"artifact_id":"only-id"}`),
		},
	}

	for _, event := range tests {
		if payload, visible := projectBrowserEvent(event); visible || payload != nil {
			t.Fatalf(
				"projectBrowserEvent(%q) = (%#v, %t), want (nil, false)",
				event.Type,
				payload,
				visible,
			)
		}
	}
}
