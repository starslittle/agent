package conversation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/starslittle/agent/go-backend/internal/agent"
	"github.com/starslittle/agent/go-backend/internal/proposals"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

const (
	DocumentExtractionAgent   = "document_extraction"
	DocumentExtractionPurpose = "document_extraction"
	DocumentExtractionVersion = "document-extraction-v1"
	maxExtractionContentRunes = 16000
)

type DocumentExtractionParams struct {
	UserID         string
	DocumentID     string
	RevisionID     string
	ContentHash    string
	Content        string
	IdempotencyKey string
	RequestID      string
}

type documentExtractionEnvelope struct {
	Kind              string `json:"kind"`
	RunPurpose        string `json:"run_purpose"`
	ExtractionVersion string `json:"extraction_version"`
	DocumentID        string `json:"document_id"`
	RevisionID        string `json:"document_revision_id"`
	ContentHash       string `json:"content_hash"`
	Markdown          string `json:"markdown"`
}

// CreateDocumentExtractionRun creates a normal Product Run in a hidden,
// deterministic conversation. The source Revision is frozen into the request.
func (s *Service) CreateDocumentExtractionRun(ctx context.Context, params DocumentExtractionParams) (Generation, error) {
	params.UserID = strings.TrimSpace(params.UserID)
	params.DocumentID = strings.TrimSpace(params.DocumentID)
	params.RevisionID = strings.TrimSpace(params.RevisionID)
	params.ContentHash = strings.ToLower(strings.TrimSpace(params.ContentHash))
	params.IdempotencyKey = strings.TrimSpace(params.IdempotencyKey)
	if params.UserID == "" || params.DocumentID == "" || params.RevisionID == "" ||
		params.ContentHash == "" || params.IdempotencyKey == "" ||
		utf8.RuneCountInString(params.Content) > maxExtractionContentRunes ||
		utf8.RuneCountInString(params.IdempotencyKey) > 128 {
		return Generation{}, ErrInvalidInput
	}
	envelope, err := json.Marshal(documentExtractionEnvelope{
		Kind: "qidian.document_extraction.v1", RunPurpose: DocumentExtractionPurpose,
		ExtractionVersion: DocumentExtractionVersion, DocumentID: params.DocumentID,
		RevisionID: params.RevisionID, ContentHash: params.ContentHash, Markdown: params.Content,
	})
	if err != nil || utf8.RuneCount(envelope) > 20000 {
		return Generation{}, ErrInvalidInput
	}
	conversationID := stableUUID("extraction-conversation", params.UserID, params.DocumentID, params.RevisionID, DocumentExtractionVersion)
	conversation, createErr := s.store.CreateConversation(ctx, conversationID, params.UserID, DocumentExtractionAgent)
	if createErr != nil {
		conversation, err = s.store.FindConversation(ctx, params.UserID, conversationID)
		if err != nil || conversation.AgentName != DocumentExtractionAgent {
			return Generation{}, createErr
		}
	}
	clientMessageID := stableUUID("extraction-message", params.UserID, params.RevisionID, DocumentExtractionVersion, params.IdempotencyKey)
	return s.CreateRun(ctx, StartGenerationParams{
		UserID: params.UserID, ConversationID: conversation.ID, ClientMessageID: clientMessageID,
		RequestID: params.RequestID, IdempotencyKey: params.IdempotencyKey, Content: string(envelope),
		AgentName: DocumentExtractionAgent, ModelID: "auto",
	})
}

type extractionCandidateEvent struct {
	CandidateType  string  `json:"candidate_type"`
	Domain         string  `json:"domain"`
	Content        string  `json:"content"`
	SourceLocation string  `json:"source_location"`
	SourceExcerpt  string  `json:"source_excerpt"`
	Confidence     float64 `json:"confidence"`
	ProposedAction string  `json:"proposed_action"`
	Explanation    string  `json:"explanation"`
}

type extractionCompletedEvent struct {
	RunPurpose        string                     `json:"run_purpose"`
	DocumentID        string                     `json:"document_id"`
	RevisionID        string                     `json:"document_revision_id"`
	ExtractionVersion string                     `json:"extraction_version"`
	PromptVersion     string                     `json:"prompt_version"`
	ModelVersion      string                     `json:"model_version"`
	Candidates        []extractionCandidateEvent `json:"candidates"`
}

type extractionWikiStore interface {
	ListWikiItems(context.Context, wiki.ListParams) ([]wiki.Item, error)
}

func (s *Service) projectDocumentExtraction(ctx context.Context, userID, runID string, event agent.Event) error {
	if event.Type != "document.extraction.completed" {
		return nil
	}
	detail, err := s.store.FindAgentRunDetail(ctx, userID, runID)
	if err != nil {
		return err
	}
	conversation, err := s.store.FindConversation(ctx, userID, detail.Run.ConversationID)
	if err != nil || conversation.AgentName != DocumentExtractionAgent {
		return errors.New("document extraction event is not owned by an extraction run")
	}
	var completed extractionCompletedEvent
	if err := json.Unmarshal(event.Data, &completed); err != nil || completed.RunPurpose != DocumentExtractionPurpose ||
		strings.TrimSpace(completed.DocumentID) == "" || strings.TrimSpace(completed.RevisionID) == "" ||
		completed.ExtractionVersion != DocumentExtractionVersion || len(completed.Candidates) > 100 {
		return ErrInvalidInput
	}
	proposalStore, ok := s.store.(proposals.Store)
	if !ok {
		return errors.New("proposal store unavailable")
	}
	proposalService := proposals.NewService(proposalStore)
	wikiStore, _ := s.store.(extractionWikiStore)
	for _, candidate := range completed.Candidates {
		if candidate.Confidence < 0 || candidate.Confidence > 1 ||
			(candidate.ProposedAction != proposals.OperationCreate && candidate.ProposedAction != proposals.OperationUpdate) {
			return ErrInvalidInput
		}
		var targetItemID, targetRevisionID *string
		var conflicts []string
		if wikiStore != nil {
			existing, listErr := wikiStore.ListWikiItems(ctx, wiki.ListParams{
				UserID: userID, Types: []string{candidate.CandidateType}, Domain: candidate.Domain,
				Statuses: []string{wiki.StatusConfirmed, wiki.StatusOutdated}, Limit: 5,
			})
			if listErr != nil {
				return listErr
			}
			for _, item := range existing {
				if strings.TrimSpace(item.Content) != strings.TrimSpace(candidate.Content) {
					conflicts = append(conflicts, item.ID)
				}
			}
			if candidate.ProposedAction == proposals.OperationUpdate && len(existing) > 0 {
				targetItemID, targetRevisionID = pointer(existing[0].ID), pointer(existing[0].CurrentRevisionID)
			}
		}
		sourceReference := fmt.Sprintf("document:%s@%s#%s", completed.DocumentID, completed.RevisionID, candidate.SourceLocation)
		sourceDetailBytes, _ := json.Marshal(map[string]any{
			"source_excerpt": candidate.SourceExcerpt, "confidence": candidate.Confidence,
			"low_confidence": candidate.Confidence < 0.65, "proposed_action": candidate.ProposedAction,
			"conflict_item_ids": conflicts, "explanation": candidate.Explanation,
			"extraction_version": completed.ExtractionVersion, "prompt_version": completed.PromptVersion,
			"model_version": completed.ModelVersion,
		})
		proposalID := stableUUID("document-proposal", userID, completed.DocumentID, completed.RevisionID,
			completed.ExtractionVersion, candidate.CandidateType, strings.ToLower(candidate.Domain),
			candidate.Content, candidate.SourceLocation)
		documentID, revisionID := completed.DocumentID, completed.RevisionID
		if _, err := proposalService.Create(ctx, proposals.CreateParams{
			ID: proposalID, UserID: userID, TargetItemID: targetItemID, TargetRevisionID: targetRevisionID,
			ItemType: candidate.CandidateType, Domain: candidate.Domain, ProposedContent: candidate.Content,
			SourceType: wiki.SourceDocumentExtracted, SourceReference: &sourceReference,
			SourceDetail: pointer(string(sourceDetailBytes)), DocumentID: &documentID,
			DocumentRevisionID: &revisionID, CreatedBy: wiki.ActorAgent,
		}); err != nil {
			// The proposal ID is derived from the immutable source revision and
			// candidate identity. A retry after the user has handled the proposal
			// can legitimately calculate different conflict metadata, but it must
			// not overwrite the audited proposal or fail the whole extraction Run.
			if errors.Is(err, proposals.ErrAlreadyExists) {
				continue
			}
			return err
		}
	}
	return nil
}

func stableUUID(parts ...string) string {
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	value := hex.EncodeToString(sum[:16])
	return fmt.Sprintf("%s-%s-5%s-a%s-%s", value[:8], value[8:12], value[13:16], value[17:20], value[20:32])
}

func pointer(value string) *string { return &value }
