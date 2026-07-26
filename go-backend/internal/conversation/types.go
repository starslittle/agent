package conversation

import (
	"encoding/json"
	"time"
)

const (
	DefaultTitle = "新的对话"
	DefaultAgent = "default_llm_agent"
)

type Conversation struct {
	ID                 string     `json:"id"`
	UserID             string     `json:"-"`
	Title              string     `json:"title"`
	AgentName          string     `json:"agent_name"`
	Status             string     `json:"status"`
	LastMessagePreview string     `json:"last_message_preview,omitempty"`
	LastMessageAt      *time.Time `json:"last_message_at,omitempty"`
	CreatedAt          time.Time  `json:"created_at"`
	UpdatedAt          time.Time  `json:"updated_at"`
}

type Message struct {
	ID              string          `json:"id"`
	ConversationID  string          `json:"conversation_id"`
	ClientMessageID *string         `json:"client_message_id,omitempty"`
	Role            string          `json:"role"`
	Content         string          `json:"content"`
	Status          string          `json:"status"`
	SequenceID      int64           `json:"sequence_id"`
	Metadata        json.RawMessage `json:"metadata,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
	CompletedAt     *time.Time      `json:"completed_at,omitempty"`
}

type Run struct {
	ID                 string
	ExecutionID        string
	ConversationID     string
	UserMessageID      string
	AssistantMessageID string
	RequestID          string
	AgentName          string
	Status             string
	ProtocolVersion    int
	LastSequence       int64
}

type Generation struct {
	Conversation Conversation
	UserMessage  Message
	Assistant    Message
	Run          Run
}

type ListParams struct {
	UserID string
	Limit  int
	Query  string
	Before *time.Time
}

type MessageListParams struct {
	UserID         string
	ConversationID string
	Limit          int
	BeforeSequence *int64
}

type StartGenerationParams struct {
	UserID          string
	ConversationID  string
	ClientMessageID string
	RequestID       string
	ExecutionID     string
	Content         string
	AgentName       string
	ProtocolVersion int
}

type FinishGenerationParams struct {
	UserID              string
	RunID               string
	AssistantMessageID  string
	Content             string
	Status              string
	ErrorCode           string
	ErrorDetail         string
	FirstTokenAt        *time.Time
	GenerationCompleted time.Time
}
