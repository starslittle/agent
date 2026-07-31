package httpapi

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/agenttrace"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

type browserActivity struct {
	ID         string `json:"id"`
	Sequence   int64  `json:"sequence,omitempty"`
	Kind       string `json:"kind"`
	Status     string `json:"status"`
	Label      string `json:"label"`
	Name       string `json:"name,omitempty"`
	DurationMS *int64 `json:"duration_ms,omitempty"`
}

type browserActivityEvent struct {
	Type     string          `json:"type"`
	Sequence int64           `json:"sequence,omitempty"`
	Activity browserActivity `json:"activity"`
}

type browserAnswerDeltaEvent struct {
	Type     string `json:"type"`
	Sequence int64  `json:"sequence,omitempty"`
	Data     string `json:"data"`
}

type browserCitationEvent struct {
	Type     string                `json:"type"`
	Sequence int64                 `json:"sequence,omitempty"`
	Citation conversation.Citation `json:"citation"`
}

type browserDoneEvent struct {
	Type      string  `json:"type"`
	Sequence  int64   `json:"sequence"`
	Status    string  `json:"status"`
	ErrorCode *string `json:"error_code,omitempty"`
}

type browserSequenceGapEvent struct {
	Type     string `json:"type"`
	Code     string `json:"code"`
	Expected int64  `json:"expected_sequence"`
	Received int64  `json:"received_sequence"`
}

type browserArtifact struct {
	ArtifactID   string `json:"artifact_id"`
	ArtifactType string `json:"artifact_type"`
	ContentHash  string `json:"content_hash"`
	MIMEType     string `json:"mime_type"`
	SizeBytes    int64  `json:"size_bytes"`
}

type browserArtifactEvent struct {
	Type     string          `json:"type"`
	Sequence int64           `json:"sequence,omitempty"`
	Artifact browserArtifact `json:"artifact"`
}

type browserEventData struct {
	Text         string `json:"text"`
	Stage        string `json:"stage"`
	Name         string `json:"name"`
	DurationMS   *int64 `json:"duration_ms"`
	ArtifactID   string `json:"artifact_id"`
	ArtifactType string `json:"artifact_type"`
	ContentHash  string `json:"content_hash"`
	MediaType    string `json:"media_type"`
	SizeBytes    *int64 `json:"size_bytes"`
}

type toolPresentation struct {
	name  string
	label string
}

var browserToolPresentations = map[string]toolPresentation{
	"tavily_search":    {name: "tavily_search", label: "联网检索"},
	"get_current_date": {name: "get_current_date", label: "日期查询"},
	"get_lunar_chart":  {name: "get_lunar_chart", label: "命盘计算"},
	"get_ziwei_chart":  {name: "get_ziwei_chart", label: "紫微排盘"},
}

func projectBrowserEvent(event agent.Event) (any, bool) {
	var data browserEventData
	if err := json.Unmarshal(event.Data, &data); err != nil {
		return nil, false
	}

	switch event.Type {
	case "answer.delta":
		if data.Text == "" {
			return nil, false
		}
		return browserAnswerDeltaEvent{
			Type:     "answer_delta",
			Sequence: event.Sequence,
			Data:     data.Text,
		}, true
	case "citation.created":
		citation, valid := conversation.ParseCitation(
			agenttrace.Sanitize(event.Data),
		)
		if !valid {
			return nil, false
		}
		return browserCitationEvent{
			Type:     "citation",
			Sequence: event.Sequence,
			Citation: citation,
		}, true
	case "artifact.created":
		if data.ArtifactID == "" ||
			data.ArtifactType == "" ||
			data.ContentHash == "" ||
			data.MediaType == "" ||
			data.SizeBytes == nil ||
			*data.SizeBytes < 0 {
			return nil, false
		}
		return browserArtifactEvent{
			Type:     "artifact",
			Sequence: event.Sequence,
			Artifact: browserArtifact{
				ArtifactID:   data.ArtifactID,
				ArtifactType: data.ArtifactType,
				ContentHash:  data.ContentHash,
				MIMEType:     data.MediaType,
				SizeBytes:    *data.SizeBytes,
			},
		}, true
	case "route.selected":
		return newBrowserActivityEvent(
			event,
			"route",
			"completed",
			"已选择执行路线",
			"",
			nil,
		), true
	case "progress":
		return newBrowserActivityEvent(
			event,
			"progress",
			"running",
			progressLabel(data.Stage),
			"",
			nil,
		), true
	case "model.started":
		return newBrowserActivityEvent(
			event,
			"model",
			"started",
			"正在生成回答",
			"",
			nil,
		), true
	case "model.completed":
		return newBrowserActivityEvent(
			event,
			"model",
			"completed",
			"回答生成完成",
			"",
			safeDuration(data.DurationMS),
		), true
	case "model.failed":
		return newBrowserActivityEvent(
			event,
			"model",
			"failed",
			"回答生成失败",
			"",
			safeDuration(data.DurationMS),
		), true
	case "tool.started", "tool.completed", "tool.failed", "tool.cancelled":
		status := strings.TrimPrefix(event.Type, "tool.")
		presentation, known := browserToolPresentations[data.Name]
		if !known {
			presentation = toolPresentation{label: "工具执行"}
		}
		return newBrowserActivityEvent(
			event,
			"tool",
			status,
			toolStatusLabel(presentation.label, status),
			presentation.name,
			safeDuration(data.DurationMS),
		), true
	default:
		return nil, false
	}
}

func projectBrowserDone(
	event agent.Event,
	status string,
	errorCode *string,
) (browserDoneEvent, bool) {
	switch event.Type {
	case "run.completed", "run.cancelled", "run.failed", "run.timed_out":
		return browserDoneEvent{
			Type:      "done",
			Sequence:  event.Sequence,
			Status:    status,
			ErrorCode: errorCode,
		}, true
	default:
		return browserDoneEvent{}, false
	}
}

func newBrowserActivityEvent(
	event agent.Event,
	kind string,
	status string,
	label string,
	name string,
	durationMS *int64,
) browserActivityEvent {
	return browserActivityEvent{
		Type:     "activity",
		Sequence: event.Sequence,
		Activity: browserActivity{
			ID:         fmt.Sprintf("%d:%s", event.Sequence, event.Type),
			Sequence:   event.Sequence,
			Kind:       kind,
			Status:     status,
			Label:      label,
			Name:       name,
			DurationMS: durationMS,
		},
	}
}

func safeDuration(durationMS *int64) *int64 {
	if durationMS == nil || *durationMS < 0 {
		return nil
	}
	return durationMS
}

func progressLabel(stage string) string {
	switch stage {
	case "research.plan":
		return "正在规划检索"
	case "research.collect":
		return "正在收集资料"
	case "research.grade":
		return "正在评估资料"
	case "research.synthesize":
		return "正在整理回答"
	default:
		return "正在处理请求"
	}
}

func toolStatusLabel(label string, status string) string {
	switch status {
	case "started":
		return "正在" + label
	case "completed":
		return label + "完成"
	case "failed":
		return label + "失败"
	case "cancelled":
		return label + "已取消"
	default:
		return label
	}
}
