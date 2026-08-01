package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/starslittle/agent/go-backend/internal/proposals"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func (s *Store) CreateWikiProposal(ctx context.Context, params proposals.CreateParams) (proposals.Proposal, error) {
	operation := proposals.OperationCreate
	if params.TargetItemID != nil {
		operation = proposals.OperationUpdate
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO app_core.wiki_update_proposals
			(id,user_id,target_item_id,target_revision_id,operation,item_type,domain,
			 proposed_content,source_type,source_ref,source_detail,document_id,
			 document_revision_id,status,created_by,created_at,updated_at)
		VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'pending',$14,$15,$15)
	`, params.ID, params.UserID, params.TargetItemID, params.TargetRevisionID, operation,
		params.ItemType, params.Domain, params.ProposedContent, params.SourceType,
		params.SourceReference, params.SourceDetail, params.DocumentID,
		params.DocumentRevisionID, params.CreatedBy, params.CreatedAt)
	if err != nil {
		return proposals.Proposal{}, mapProposalError(err)
	}
	return s.FindWikiProposal(ctx, params.UserID, params.ID)
}

func (s *Store) FindWikiProposal(ctx context.Context, userID, proposalID string) (proposals.Proposal, error) {
	var proposal proposals.Proposal
	err := s.pool.QueryRow(ctx, proposalSelect+` WHERE user_id=$1 AND id=$2`, userID, proposalID).Scan(proposalScanTargets(&proposal)...)
	return proposal, mapProposalError(err)
}

func (s *Store) ListWikiProposals(ctx context.Context, params proposals.ListParams) ([]proposals.Proposal, error) {
	rows, err := s.pool.Query(ctx, proposalSelect+`
		WHERE user_id=$1
			AND ($2::text[] IS NULL OR status=ANY($2))
			AND ($3::uuid IS NULL OR document_id=$3)
		ORDER BY updated_at DESC,id DESC LIMIT $4 OFFSET $5
	`, params.UserID, nullableStrings(params.Statuses), params.DocumentID, params.Limit, params.Offset)
	if err != nil {
		return nil, mapProposalError(err)
	}
	defer rows.Close()
	items := []proposals.Proposal{}
	for rows.Next() {
		var proposal proposals.Proposal
		if err := rows.Scan(proposalScanTargets(&proposal)...); err != nil {
			return nil, mapProposalError(err)
		}
		items = append(items, proposal)
	}
	return items, rows.Err()
}

func (s *Store) ResolveWikiProposal(ctx context.Context, params proposals.ResolveParams) (proposals.Resolution, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return proposals.Resolution{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var replayProposalID, replayAction, replayHash string
	var replayJSON []byte
	err = tx.QueryRow(ctx, `SELECT proposal_id::text,action,request_hash,result FROM app_core.wiki_proposal_actions WHERE user_id=$1 AND idempotency_key=$2 FOR UPDATE`, params.UserID, params.IdempotencyKey).Scan(&replayProposalID, &replayAction, &replayHash, &replayJSON)
	if err == nil {
		if replayProposalID != params.ProposalID || replayAction != params.Action || replayHash != params.RequestHash {
			return proposals.Resolution{}, proposals.ErrIdempotencyConflict
		}
		var result proposals.Resolution
		if json.Unmarshal(replayJSON, &result) != nil {
			return proposals.Resolution{}, errors.New("invalid stored proposal result")
		}
		result.Replayed = true
		return result, tx.Commit(ctx)
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return proposals.Resolution{}, mapProposalError(err)
	}

	var proposal proposals.Proposal
	if err := tx.QueryRow(ctx, proposalSelect+` WHERE user_id=$1 AND id=$2 FOR UPDATE`, params.UserID, params.ProposalID).Scan(proposalScanTargets(&proposal)...); err != nil {
		return proposals.Resolution{}, mapProposalError(err)
	}
	// A concurrent request with the same key can observe no action before it
	// waits on the proposal lock. Recheck after acquiring that lock so the
	// committed first result is replayed instead of reported as a state error.
	err = tx.QueryRow(ctx, `SELECT proposal_id::text,action,request_hash,result FROM app_core.wiki_proposal_actions WHERE user_id=$1 AND idempotency_key=$2`, params.UserID, params.IdempotencyKey).Scan(&replayProposalID, &replayAction, &replayHash, &replayJSON)
	if err == nil {
		if replayProposalID != params.ProposalID || replayAction != params.Action || replayHash != params.RequestHash {
			return proposals.Resolution{}, proposals.ErrIdempotencyConflict
		}
		var result proposals.Resolution
		if json.Unmarshal(replayJSON, &result) != nil {
			return proposals.Resolution{}, errors.New("invalid stored proposal result")
		}
		result.Replayed = true
		return result, tx.Commit(ctx)
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return proposals.Resolution{}, mapProposalError(err)
	}
	if proposal.Status != proposals.StatusPending && proposal.Status != proposals.StatusDeferred {
		return proposals.Resolution{}, proposals.ErrInvalidState
	}

	var appliedItemID, appliedRevisionID *string
	switch params.Action {
	case proposals.ActionDefer:
		if err := updateProposalResolution(ctx, tx, &proposal, proposals.StatusDeferred, params, nil, nil, nil); err != nil {
			return proposals.Resolution{}, err
		}
	case proposals.ActionReject:
		if err := updateProposalResolution(ctx, tx, &proposal, proposals.StatusRejected, params, nil, nil, nil); err != nil {
			return proposals.Resolution{}, err
		}
	case proposals.ActionAccept:
		if proposal.SourceType == wiki.SourceFortuneNarrative {
			return proposals.Resolution{}, proposals.ErrInvalidState
		}
		content := proposal.ProposedContent
		if params.FinalContent != nil {
			content = *params.FinalContent
		}
		itemID, revisionID, applyErr := applyProposalToWiki(ctx, tx, proposal, params, content)
		if applyErr != nil {
			return proposals.Resolution{}, applyErr
		}
		appliedItemID, appliedRevisionID = &itemID, &revisionID
		if proposal.Operation == proposals.OperationUpdate {
			if _, err := tx.Exec(ctx, `
				UPDATE app_core.wiki_update_proposals
				SET status='superseded',resolution_action=NULL,resolved_by_user_id=NULL,
					resolved_at=NULL,final_content=NULL,version=version+1,updated_at=$5
				WHERE user_id=$1 AND id<>$2 AND target_item_id=$3 AND target_revision_id=$4
					AND status IN ('pending','deferred')
			`, params.UserID, proposal.ID, proposal.TargetItemID, proposal.TargetRevisionID, params.ResolvedAt); err != nil {
				return proposals.Resolution{}, mapProposalError(err)
			}
		}
		if err := updateProposalResolution(ctx, tx, &proposal, proposals.StatusAccepted, params, &content, &itemID, &revisionID); err != nil {
			return proposals.Resolution{}, err
		}
	default:
		return proposals.Resolution{}, proposals.ErrInvalidInput
	}

	result := proposals.Resolution{Proposal: proposal, AppliedItemID: appliedItemID, AppliedRevisionID: appliedRevisionID}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return proposals.Resolution{}, err
	}
	if _, err := tx.Exec(ctx, `INSERT INTO app_core.wiki_proposal_actions(id,user_id,proposal_id,idempotency_key,action,request_hash,result,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)`, params.ActionID, params.UserID, proposal.ID, params.IdempotencyKey, params.Action, params.RequestHash, resultJSON, params.ResolvedAt); err != nil {
		return proposals.Resolution{}, mapProposalError(err)
	}
	if err := tx.Commit(ctx); err != nil {
		return proposals.Resolution{}, mapProposalError(err)
	}
	return result, nil
}

func applyProposalToWiki(ctx context.Context, tx pgx.Tx, proposal proposals.Proposal, params proposals.ResolveParams, content string) (string, string, error) {
	itemID, revisionID := params.ItemID, params.RevisionID
	if proposal.Operation == proposals.OperationCreate {
		if _, err := tx.Exec(ctx, `
			INSERT INTO app_core.wiki_items(id,user_id,item_type,domain,status,confirmed_by_user,created_at,updated_at)
			VALUES($1,$2,$3,$4,'confirmed',TRUE,$5,$5)
		`, itemID, params.UserID, proposal.ItemType, proposal.Domain, params.ResolvedAt); err != nil {
			return "", "", mapProposalError(err)
		}
		if _, err := tx.Exec(ctx, `INSERT INTO app_core.wiki_item_revisions(id,item_id,user_id,revision_number,content,created_by,created_at) VALUES($1,$2,$3,1,$4,'user',$5)`, revisionID, itemID, params.UserID, content, params.ResolvedAt); err != nil {
			return "", "", mapProposalError(err)
		}
	} else {
		if proposal.TargetItemID == nil || proposal.TargetRevisionID == nil {
			return "", "", proposals.ErrVersionConflict
		}
		itemID = *proposal.TargetItemID
		var currentRevision, status, itemType, domain string
		var currentVersion, nextRevision int64
		if err := tx.QueryRow(ctx, `SELECT current_revision_id::text,status,item_type,domain,version FROM app_core.wiki_items WHERE user_id=$1 AND id=$2 FOR UPDATE`, params.UserID, itemID).Scan(&currentRevision, &status, &itemType, &domain, &currentVersion); err != nil {
			return "", "", mapProposalError(err)
		}
		if currentRevision != *proposal.TargetRevisionID || itemType != proposal.ItemType || domain != proposal.Domain {
			return "", "", proposals.ErrVersionConflict
		}
		if status == wiki.StatusForgotten || status == wiki.StatusRejected {
			return "", "", proposals.ErrInvalidState
		}
		if err := tx.QueryRow(ctx, `SELECT COALESCE(MAX(revision_number),0)+1 FROM app_core.wiki_item_revisions WHERE user_id=$1 AND item_id=$2`, params.UserID, itemID).Scan(&nextRevision); err != nil {
			return "", "", mapProposalError(err)
		}
		if _, err := tx.Exec(ctx, `INSERT INTO app_core.wiki_item_revisions(id,item_id,user_id,revision_number,content,created_by,replaces_revision_id,created_at) VALUES($1,$2,$3,$4,$5,'user',$6,$7)`, revisionID, itemID, params.UserID, nextRevision, content, currentRevision, params.ResolvedAt); err != nil {
			return "", "", mapProposalError(err)
		}
		if _, err := tx.Exec(ctx, `UPDATE app_core.wiki_items SET status='confirmed',status_before_forgotten=NULL,current_revision_id=$3,confirmed_by_user=TRUE,version=version+1,updated_at=$4 WHERE user_id=$1 AND id=$2 AND version=$5`, params.UserID, itemID, revisionID, params.ResolvedAt, currentVersion); err != nil {
			return "", "", mapProposalError(err)
		}
	}
	source := wiki.SourceInput{ID: params.SourceID, Type: proposal.SourceType, Reference: proposal.SourceReference, Detail: proposal.SourceDetail, DocumentID: proposal.DocumentID, DocumentRevisionID: proposal.DocumentRevisionID}
	if err := insertWikiSource(ctx, tx, params.UserID, itemID, revisionID, source, params.ResolvedAt); err != nil {
		return "", "", mapProposalError(err)
	}
	proposalReference := proposal.ID
	if err := insertWikiSource(ctx, tx, params.UserID, itemID, revisionID, wiki.SourceInput{ID: params.ConfirmationID, Type: wiki.SourceUserConfirmed, Reference: &proposalReference}, params.ResolvedAt); err != nil {
		return "", "", mapProposalError(err)
	}
	if proposal.Operation == proposals.OperationCreate {
		if _, err := tx.Exec(ctx, `UPDATE app_core.wiki_items SET current_revision_id=$3 WHERE user_id=$1 AND id=$2`, params.UserID, itemID, revisionID); err != nil {
			return "", "", mapProposalError(err)
		}
	}
	return itemID, revisionID, nil
}

func updateProposalResolution(ctx context.Context, tx pgx.Tx, proposal *proposals.Proposal, status string, params proposals.ResolveParams, content, itemID, revisionID *string) error {
	err := tx.QueryRow(ctx, `
		UPDATE app_core.wiki_update_proposals
		SET status=$3,final_content=$4,resolution_action=$5,resolved_by_user_id=$1,
			resolved_at=$6,applied_item_id=$7,applied_revision_id=$8,
			version=version+1,updated_at=$6
		WHERE user_id=$1 AND id=$2 AND version=$9
		RETURNING `+proposalReturning, params.UserID, proposal.ID, status, content, params.Action,
		params.ResolvedAt, itemID, revisionID, proposal.Version).Scan(proposalScanTargets(proposal)...)
	return mapProposalError(err)
}

const proposalSelect = `SELECT ` + proposalReturning + ` FROM app_core.wiki_update_proposals`
const proposalReturning = `id::text,target_item_id::text,target_revision_id::text,operation,
	item_type,domain,proposed_content,source_type,source_ref,source_detail,
	document_id::text,document_revision_id::text,status,final_content,resolution_action,
	resolved_by_user_id::text,resolved_at,applied_item_id::text,applied_revision_id::text,
	created_by,version,created_at,updated_at`

func proposalScanTargets(proposal *proposals.Proposal) []any {
	return []any{&proposal.ID, &proposal.TargetItemID, &proposal.TargetRevisionID, &proposal.Operation,
		&proposal.ItemType, &proposal.Domain, &proposal.ProposedContent, &proposal.SourceType,
		&proposal.SourceReference, &proposal.SourceDetail, &proposal.DocumentID,
		&proposal.DocumentRevisionID, &proposal.Status, &proposal.FinalContent,
		&proposal.ResolutionAction, &proposal.ResolvedByUserID, &proposal.ResolvedAt,
		&proposal.AppliedItemID, &proposal.AppliedRevisionID, &proposal.CreatedBy,
		&proposal.Version, &proposal.CreatedAt, &proposal.UpdatedAt}
}

func mapProposalError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return proposals.ErrNotFound
	}
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) {
		switch pgError.Code {
		case "23505":
			return proposals.ErrAlreadyExists
		case "23514", "22P02":
			return proposals.ErrInvalidInput
		case "23503":
			return proposals.ErrNotFound
		}
	}
	if strings.Contains(err.Error(), "proposal") {
		return fmt.Errorf("proposal store: %w", err)
	}
	return err
}
