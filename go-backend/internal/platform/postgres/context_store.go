package postgres

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5"
	"github.com/starslittle/agent/go-backend/internal/agent"
	contextpackage "github.com/starslittle/agent/go-backend/internal/context"
	"github.com/starslittle/agent/go-backend/internal/conversation"
)

func (s *Store) PrepareContextPackage(ctx context.Context, userID, runID, packageID string, resolution agent.SkillResolution, requirements contextpackage.Requirements) (contextpackage.Package, error) {
	if err := requirements.Validate(); err != nil {
		return contextpackage.Package{}, err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return contextpackage.Package{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var existing *string
	if err := tx.QueryRow(ctx, `SELECT r.context_package_id::text FROM app_core.agent_runs r JOIN app_core.conversations c ON c.id=r.conversation_id WHERE r.id=$1 AND c.user_id=$2 FOR UPDATE OF r`, runID, userID).Scan(&existing); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return contextpackage.Package{}, conversation.ErrNotFound
		}
		return contextpackage.Package{}, err
	}
	if existing != nil {
		resolution.ContextPackageID = existing
		if err := sealSkillResolution(ctx, tx, runID, resolution); err != nil {
			return contextpackage.Package{}, err
		}
		pkg, err := findContextPackage(ctx, tx, userID, runID)
		if err != nil {
			return contextpackage.Package{}, err
		}
		return pkg, tx.Commit(ctx)
	}

	candidates, err := listContextCandidates(ctx, tx, userID, requirements)
	if err != nil {
		return contextpackage.Package{}, err
	}
	pkg, err := contextpackage.Assemble(packageID, runID, requirements, candidates)
	if err != nil {
		return contextpackage.Package{}, err
	}
	requirementsJSON, _ := json.Marshal(requirements)
	policyJSON, _ := json.Marshal(pkg.Policy)
	if _, err := tx.Exec(ctx, `
		INSERT INTO app_core.context_packages
			(id,user_id,run_id,purpose,requirements,policy,item_budget,character_budget)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
	`, pkg.PackageID, userID, runID, pkg.Purpose, requirementsJSON, policyJSON, requirements.ItemBudget, requirements.CharacterBudget); err != nil {
		return contextpackage.Package{}, err
	}
	for rank, item := range pkg.Items {
		source, _ := json.Marshal(item.Source)
		if _, err := tx.Exec(ctx, `
			INSERT INTO app_core.context_package_items
				(package_id,user_id,item_id,revision_id,item_type,domain,content,source,item_updated_at,rank)
			VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		`, pkg.PackageID, userID, item.ItemID, item.RevisionID, item.Type, item.Domain, item.Content, source, item.UpdatedAt, rank+1); err != nil {
			return contextpackage.Package{}, err
		}
	}
	resolution.ContextPackageID = &pkg.PackageID
	if err := sealSkillResolution(ctx, tx, runID, resolution); err != nil {
		return contextpackage.Package{}, err
	}
	routeUsage, _ := json.Marshal(resolution.RouteUsage)
	if _, err := tx.Exec(ctx, `UPDATE app_core.agent_runs SET metadata=metadata || jsonb_build_object('route_usage',$2::jsonb) WHERE id=$1`, runID, routeUsage); err != nil {
		return contextpackage.Package{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return contextpackage.Package{}, err
	}
	return pkg, nil
}

func (s *Store) FindContextPackageByRun(ctx context.Context, userID, runID string) (contextpackage.Package, error) {
	return findContextPackage(ctx, s.pool, userID, runID)
}

type contextQuerier interface {
	QueryRow(context.Context, string, ...any) pgx.Row
	Query(context.Context, string, ...any) (pgx.Rows, error)
}

func findContextPackage(ctx context.Context, q contextQuerier, userID, runID string) (contextpackage.Package, error) {
	var pkg contextpackage.Package
	var requirementsJSON, policyJSON []byte
	if err := q.QueryRow(ctx, `SELECT id::text,run_id::text,purpose,requirements,policy,created_at FROM app_core.context_packages WHERE user_id=$1 AND run_id=$2`, userID, runID).Scan(&pkg.PackageID, &pkg.RunID, &pkg.Purpose, &requirementsJSON, &policyJSON, &pkg.CreatedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return contextpackage.Package{}, conversation.ErrNotFound
		}
		return contextpackage.Package{}, err
	}
	if err := json.Unmarshal(requirementsJSON, &pkg.Requirements); err != nil {
		return contextpackage.Package{}, err
	}
	if err := json.Unmarshal(policyJSON, &pkg.Policy); err != nil {
		return contextpackage.Package{}, err
	}
	rows, err := q.Query(ctx, `SELECT item_id::text,revision_id::text,item_type,domain,content,source,item_updated_at FROM app_core.context_package_items WHERE package_id=$1 AND user_id=$2 AND redacted_at IS NULL ORDER BY rank`, pkg.PackageID, userID)
	if err != nil {
		return contextpackage.Package{}, err
	}
	defer rows.Close()
	pkg.Items = []contextpackage.Item{}
	for rows.Next() {
		var item contextpackage.Item
		var source []byte
		if err := rows.Scan(&item.ItemID, &item.RevisionID, &item.Type, &item.Domain, &item.Content, &source, &item.UpdatedAt); err != nil {
			return contextpackage.Package{}, err
		}
		if err := json.Unmarshal(source, &item.Source); err != nil {
			return contextpackage.Package{}, err
		}
		pkg.Items = append(pkg.Items, item)
	}
	return pkg, rows.Err()
}

func listContextCandidates(ctx context.Context, q contextQuerier, userID string, requirements contextpackage.Requirements) ([]contextpackage.Candidate, error) {
	if !requirements.NeedsPersonalContext {
		return []contextpackage.Candidate{}, nil
	}
	rows, err := q.Query(ctx, `
		SELECT i.id::text,r.id::text,i.item_type,i.domain,r.content,i.updated_at,i.confirmed_by_user,
			COALESCE(s.source_type,'user_confirmed'),s.source_ref,s.source_detail
		FROM app_core.wiki_items i
		JOIN app_core.wiki_item_revisions r ON r.id=i.current_revision_id AND r.item_id=i.id AND r.user_id=i.user_id
		LEFT JOIN LATERAL (
			SELECT source_type,source_ref,source_detail FROM app_core.wiki_item_sources
			WHERE user_id=i.user_id AND item_id=i.id AND revision_id=r.id ORDER BY created_at DESC LIMIT 1
		) s ON true
		WHERE i.user_id=$1 AND i.status='confirmed' AND i.confirmed_by_user=true
			AND (i.effective_at IS NULL OR i.effective_at <= NOW())
			AND i.item_type=ANY($2::text[])
			AND (cardinality($3::text[])=0 OR i.domain=ANY($3::text[]))
		ORDER BY i.updated_at DESC,i.id
	`, userID, requirements.AllowedTypes, requirements.AllowedDomains)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []contextpackage.Candidate{}
	for rows.Next() {
		var item contextpackage.Candidate
		if err := rows.Scan(&item.ItemID, &item.RevisionID, &item.Type, &item.Domain, &item.Content, &item.UpdatedAt, &item.ConfirmedByUser, &item.Source.Type, &item.Source.Reference, &item.Source.Detail); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) ListContextUsageForItem(ctx context.Context, userID, itemID string) ([]contextpackage.Usage, error) {
	rows, err := s.pool.Query(ctx, `SELECT p.id::text,p.run_id::text,p.purpose,i.revision_id::text,i.item_type,i.domain,i.source,i.item_updated_at,i.redacted_at FROM app_core.context_package_items i JOIN app_core.context_packages p ON p.id=i.package_id AND p.user_id=i.user_id WHERE i.user_id=$1 AND i.item_id=$2 ORDER BY p.created_at DESC LIMIT 50`, userID, itemID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []contextpackage.Usage{}
	for rows.Next() {
		var usage contextpackage.Usage
		var item contextpackage.UsageItem
		var source []byte
		var revision *string
		if err := rows.Scan(&usage.PackageID, &usage.RunID, &usage.Purpose, &revision, &item.Type, &item.Domain, &source, &item.UpdatedAt, &item.RedactedAt); err != nil {
			return nil, err
		}
		item.ItemID = &itemID
		item.RevisionID = revision
		_ = json.Unmarshal(source, &item.Source)
		usage.Items = []contextpackage.UsageItem{item}
		result = append(result, usage)
	}
	return result, rows.Err()
}

func redactContextForWikiItem(ctx context.Context, tx pgx.Tx, userID, itemID string) error {
	_, err := tx.Exec(ctx, `UPDATE app_core.context_package_items SET content='',redacted_at=NOW() WHERE user_id=$1 AND item_id=$2`, userID, itemID)
	return err
}
