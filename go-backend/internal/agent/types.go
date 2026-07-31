package agent

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

const ProtocolVersion = 1

type Status string

const (
	StatusQueued          Status = "queued"
	StatusRunning         Status = "running"
	StatusCancelRequested Status = "cancel_requested"
	StatusCompleted       Status = "completed"
	StatusCancelled       Status = "cancelled"
	StatusFailed          Status = "failed"
	StatusTimedOut        Status = "timed_out"
)

var transitions = map[Status]map[Status]bool{
	StatusQueued: {
		StatusRunning: true, StatusCancelRequested: true,
		StatusFailed: true, StatusTimedOut: true,
	},
	StatusRunning: {
		StatusCancelRequested: true, StatusCompleted: true,
		StatusFailed: true, StatusTimedOut: true,
	},
	StatusCancelRequested: {
		StatusCancelled: true, StatusFailed: true, StatusTimedOut: true,
	},
	StatusCompleted: {},
	StatusCancelled: {},
	StatusFailed:    {},
	StatusTimedOut:  {},
}

func (s Status) Terminal() bool {
	return s == StatusCompleted || s == StatusCancelled ||
		s == StatusFailed || s == StatusTimedOut
}

func CanTransition(from, to Status) bool {
	return from == to || transitions[from][to]
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type RunRequest struct {
	ProtocolVersion  int            `json:"protocol_version"`
	ExecutionID      string         `json:"execution_id"`
	RunID            string         `json:"run_id"`
	RequestID        string         `json:"request_id"`
	IdempotencyKey   string         `json:"idempotency_key"`
	ConversationID   string         `json:"conversation_id"`
	AgentName        string         `json:"agent_name"`
	ModelID          string         `json:"model_id"`
	RequestedSkill   *string        `json:"requested_skill"`
	ResolvedSkills   []string       `json:"resolved_skills"`
	PrimarySkill     *string        `json:"primary_skill"`
	SelectionSource  *string        `json:"selection_source"`
	ContextPackageID *string        `json:"context_package_id"`
	Mode             string         `json:"mode,omitempty"`
	Query            string         `json:"query"`
	Messages         []Message      `json:"messages"`
	DeadlineMS       int64          `json:"deadline_ms"`
	Shadow           bool           `json:"shadow"`
	Metadata         map[string]any `json:"metadata,omitempty"`
	UserID           string         `json:"-"`
}

type NormalizedRunSelection struct {
	ModelID        string
	RequestedSkill *string
	AgentName      string
}

var legacyAgentSkills = map[string]*string{
	"default":           nil,
	"default_llm_agent": nil,
	"chat":              nil,
	"chat_v1":           nil,
	"research":          stringPointer("research"),
	"research_agent":    stringPointer("research"),
	"research_v1":       stringPointer("research"),
	"general_rag_agent": stringPointer("research"),
	"fortune":           stringPointer("fortune"),
	"fortune_agent":     stringPointer("fortune"),
	"fortune_v1":        stringPointer("fortune"),
}

var skillAgentNames = map[string]string{
	"research": "research_agent",
	"fortune":  "fortune_agent",
}

func stringPointer(value string) *string {
	copy := value
	return &copy
}

func NormalizeRunSelection(
	modelID string,
	requestedSkill *string,
	agentName string,
) (NormalizedRunSelection, error) {
	modelID = strings.TrimSpace(modelID)
	if modelID == "" {
		modelID = "auto"
	}
	if modelID != "auto" {
		return NormalizedRunSelection{}, errors.New("unknown model_id")
	}
	agentName = strings.TrimSpace(agentName)
	if agentName == "" {
		agentName = "default_llm_agent"
	}
	if requestedSkill != nil {
		skill := strings.TrimSpace(*requestedSkill)
		expectedAgent, ok := skillAgentNames[skill]
		if !ok || skill == "" {
			return NormalizedRunSelection{}, errors.New("unknown requested_skill")
		}
		if agentName != "default_llm_agent" && agentName != skill &&
			agentName != expectedAgent && agentName != skill+"_v1" {
			return NormalizedRunSelection{}, errors.New(
				"requested_skill conflicts with agent_name",
			)
		}
		return NormalizedRunSelection{
			ModelID:        modelID,
			RequestedSkill: stringPointer(skill),
			AgentName:      skill,
		}, nil
	}
	legacySkill, ok := legacyAgentSkills[agentName]
	if !ok {
		return NormalizedRunSelection{}, errors.New("unknown agent_name")
	}
	normalizedAgent := "default_llm_agent"
	if legacySkill != nil {
		normalizedAgent = skillAgentNames[*legacySkill]
		if agentName == *legacySkill {
			normalizedAgent = agentName
		}
	}
	return NormalizedRunSelection{
		ModelID:        modelID,
		RequestedSkill: legacySkill,
		AgentName:      normalizedAgent,
	}, nil
}

func (r RunRequest) normalized() (RunRequest, error) {
	selection, err := NormalizeRunSelection(r.ModelID, r.RequestedSkill, r.AgentName)
	if err != nil {
		return RunRequest{}, err
	}
	r.ModelID = selection.ModelID
	r.RequestedSkill = selection.RequestedSkill
	r.AgentName = selection.AgentName
	if r.ResolvedSkills == nil {
		r.ResolvedSkills = []string{}
	}
	return r, nil
}

func (r RunRequest) MarshalJSON() ([]byte, error) {
	normalized, err := r.normalized()
	if err != nil {
		return nil, err
	}
	type wireRunRequest RunRequest
	return json.Marshal(wireRunRequest(normalized))
}

func (r RunRequest) Validate() error {
	if r.ProtocolVersion != ProtocolVersion {
		return fmt.Errorf("unsupported protocol version %d", r.ProtocolVersion)
	}
	if _, err := r.normalized(); err != nil {
		return err
	}
	for name, value := range map[string]string{
		"execution_id": r.ExecutionID,
		"run_id":       r.RunID,
		"request_id":   r.RequestID,
		"idempotency":  r.IdempotencyKey,
		"conversation": r.ConversationID,
		"query":        r.Query,
	} {
		if value == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	return nil
}

type SkillResolution struct {
	ModelID          string          `json:"model_id"`
	RequestedSkill   *string         `json:"requested_skill"`
	ResolvedSkills   []string        `json:"resolved_skills"`
	PrimarySkill     *string         `json:"primary_skill"`
	SelectionSource  string          `json:"selection_source"`
	SkillSnapshot    json.RawMessage `json:"skill_snapshot"`
	ModelSnapshot    json.RawMessage `json:"model_snapshot"`
	ContextPackageID *string         `json:"context_package_id"`
}

func ParseSkillResolution(raw json.RawMessage) (SkillResolution, error) {
	var resolution SkillResolution
	if err := json.Unmarshal(raw, &resolution); err != nil {
		return SkillResolution{}, errors.New("invalid skill resolution event")
	}
	if resolution.ModelID != "auto" || len(resolution.ResolvedSkills) > 1 {
		return SkillResolution{}, errors.New("invalid skill resolution projection")
	}
	for _, skill := range resolution.ResolvedSkills {
		if _, ok := skillAgentNames[skill]; !ok {
			return SkillResolution{}, errors.New("unknown resolved skill")
		}
	}
	if len(resolution.ResolvedSkills) == 0 {
		if resolution.PrimarySkill != nil {
			return SkillResolution{}, errors.New("direct run cannot have primary skill")
		}
		if resolution.SelectionSource != "direct" &&
			resolution.SelectionSource != "fallback" {
			return SkillResolution{}, errors.New("invalid direct selection source")
		}
	} else if resolution.PrimarySkill == nil ||
		*resolution.PrimarySkill != resolution.ResolvedSkills[0] {
		return SkillResolution{}, errors.New("primary skill must match resolution")
	}
	if resolution.RequestedSkill != nil {
		if _, ok := skillAgentNames[*resolution.RequestedSkill]; !ok {
			return SkillResolution{}, errors.New("unknown requested skill")
		}
	}
	switch resolution.SelectionSource {
	case "direct", "user", "compatibility", "automatic", "fallback":
	default:
		return SkillResolution{}, errors.New("unknown selection source")
	}
	if len(resolution.ModelSnapshot) == 0 || string(resolution.ModelSnapshot) == "null" {
		return SkillResolution{}, errors.New("model snapshot is required")
	}
	return resolution, nil
}

type Event struct {
	ProtocolVersion    int             `json:"protocol_version"`
	ExecutionID        string          `json:"execution_id"`
	RunID              string          `json:"run_id"`
	Sequence           int64           `json:"sequence"`
	Type               string          `json:"type"`
	OccurredAt         time.Time       `json:"occurred_at"`
	TraceID            string          `json:"trace_id,omitempty"`
	SpanID             string          `json:"span_id,omitempty"`
	ParentSpanID       string          `json:"parent_span_id,omitempty"`
	Category           string          `json:"category,omitempty"`
	Stage              string          `json:"stage,omitempty"`
	EventSchemaVersion int             `json:"event_schema_version,omitempty"`
	ContentCapture     string          `json:"content_capture_level,omitempty"`
	Data               json.RawMessage `json:"data"`
}

func (e Event) Validate(expectedExecutionID string) error {
	if e.ProtocolVersion != ProtocolVersion {
		return fmt.Errorf("unsupported event protocol version %d", e.ProtocolVersion)
	}
	if e.ExecutionID == "" || e.ExecutionID != expectedExecutionID {
		return errors.New("event execution_id mismatch")
	}
	if e.RunID == "" || e.Sequence < 1 || e.Type == "" || e.OccurredAt.IsZero() {
		return errors.New("event is missing required fields")
	}
	if len(e.Data) == 0 {
		e.Data = json.RawMessage(`{}`)
	}
	return nil
}

func (e Event) SSEID() string {
	return fmt.Sprintf("%s:%d", e.ExecutionID, e.Sequence)
}

type Snapshot struct {
	ProtocolVersion int            `json:"protocol_version"`
	ServiceVersion  string         `json:"service_version"`
	ExecutionID     string         `json:"execution_id"`
	RunID           string         `json:"run_id"`
	Status          Status         `json:"status"`
	LastSequence    int64          `json:"last_sequence"`
	StartedAt       *time.Time     `json:"started_at,omitempty"`
	CompletedAt     *time.Time     `json:"completed_at,omitempty"`
	ExpiresAt       time.Time      `json:"expires_at"`
	Error           map[string]any `json:"error,omitempty"`
}
