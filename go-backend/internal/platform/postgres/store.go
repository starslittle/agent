package postgres

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"sort"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/starslittle/agent/go-backend/internal/auth"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

type Store struct {
	pool *pgxpool.Pool
}

func Open(ctx context.Context, databaseURL string) (*Store, error) {
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse PostgreSQL configuration: %w", err)
	}
	config.MaxConns = 20
	config.MinConns = 1
	config.MaxConnLifetime = 30 * time.Minute
	config.MaxConnIdleTime = 5 * time.Minute
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("open PostgreSQL pool: %w", err)
	}
	store := &Store{pool: pool}
	if err := store.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping PostgreSQL: %w", err)
	}
	return store, nil
}

func (s *Store) Close() {
	s.pool.Close()
}

func (s *Store) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *Store) Migrate(ctx context.Context) error {
	connection, err := s.pool.Acquire(ctx)
	if err != nil {
		return fmt.Errorf("acquire migration connection: %w", err)
	}
	defer connection.Release()

	if _, err := connection.Exec(ctx, "SELECT pg_advisory_lock($1)", int64(71624026)); err != nil {
		return fmt.Errorf("acquire migration lock: %w", err)
	}
	defer func() {
		_, _ = connection.Exec(context.Background(), "SELECT pg_advisory_unlock($1)", int64(71624026))
	}()

	if _, err := connection.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS public.go_schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`); err != nil {
		return fmt.Errorf("create migration table: %w", err)
	}

	files, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return fmt.Errorf("list migrations: %w", err)
	}
	sort.Strings(files)
	for _, path := range files {
		applied := false
		if err := connection.QueryRow(
			ctx,
			"SELECT EXISTS (SELECT 1 FROM public.go_schema_migrations WHERE version=$1)",
			path,
		).Scan(&applied); err != nil {
			return fmt.Errorf("check migration %s: %w", path, err)
		}
		if applied {
			continue
		}
		content, err := migrationFiles.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read migration %s: %w", path, err)
		}
		transaction, err := connection.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin migration %s: %w", path, err)
		}
		if _, err := transaction.Exec(ctx, string(content)); err != nil {
			_ = transaction.Rollback(ctx)
			return fmt.Errorf("execute migration %s: %w", path, err)
		}
		if _, err := transaction.Exec(
			ctx,
			"INSERT INTO public.go_schema_migrations(version) VALUES ($1)",
			path,
		); err != nil {
			_ = transaction.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", path, err)
		}
		if err := transaction.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", path, err)
		}
	}
	return nil
}

func (s *Store) CreateUser(
	ctx context.Context,
	params auth.CreateUserParams,
) (auth.User, error) {
	transaction, err := s.pool.Begin(ctx)
	if err != nil {
		return auth.User{}, err
	}
	defer func() { _ = transaction.Rollback(ctx) }()

	var user auth.User
	err = transaction.QueryRow(ctx, `
		INSERT INTO app_core.users (id, email, display_name)
		VALUES ($1, $2, $3)
		RETURNING id::text, email, display_name, status, created_at
	`, params.ID, params.Email, params.DisplayName).Scan(
		&user.ID,
		&user.Email,
		&user.DisplayName,
		&user.Status,
		&user.CreatedAt,
	)
	if err != nil {
		var pgError *pgconn.PgError
		if errors.As(err, &pgError) && pgError.Code == "23505" {
			return auth.User{}, auth.ErrEmailExists
		}
		return auth.User{}, err
	}
	if _, err := transaction.Exec(ctx, `
		INSERT INTO app_core.auth_identities
			(id, user_id, provider, provider_subject, email, email_verified)
		VALUES ($1, $2, 'password', $3, $3, FALSE)
	`, auth.NewID(), params.ID, params.Email); err != nil {
		return auth.User{}, err
	}
	if _, err := transaction.Exec(ctx, `
		INSERT INTO app_core.password_credentials (user_id, password_hash)
		VALUES ($1, $2)
	`, params.ID, params.PasswordHash); err != nil {
		return auth.User{}, err
	}
	if err := transaction.Commit(ctx); err != nil {
		return auth.User{}, err
	}
	return user, nil
}

func (s *Store) FindCredentialByEmail(
	ctx context.Context,
	email string,
) (auth.Credential, error) {
	var credential auth.Credential
	err := s.pool.QueryRow(ctx, `
		SELECT
			u.id::text,
			u.email,
			u.display_name,
			u.status,
			u.created_at,
			p.password_hash
		FROM app_core.users u
		JOIN app_core.password_credentials p ON p.user_id = u.id
		WHERE LOWER(u.email) = LOWER($1)
	`, email).Scan(
		&credential.User.ID,
		&credential.User.Email,
		&credential.User.DisplayName,
		&credential.User.Status,
		&credential.User.CreatedAt,
		&credential.PasswordHash,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return auth.Credential{}, auth.ErrInvalidCredentials
	}
	return credential, err
}

func (s *Store) CreateSession(
	ctx context.Context,
	params auth.CreateSessionParams,
) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO app_core.sessions
			(id, user_id, token_hash, csrf_token, user_agent, expires_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`,
		params.ID,
		params.UserID,
		params.TokenHash,
		params.CSRFToken,
		params.UserAgent,
		params.ExpiresAt,
	)
	return err
}

func (s *Store) FindSession(
	ctx context.Context,
	tokenHash []byte,
	now time.Time,
) (auth.Session, error) {
	var session auth.Session
	err := s.pool.QueryRow(ctx, `
		SELECT
			s.id::text,
			s.csrf_token,
			s.created_at,
			s.last_seen_at,
			s.expires_at,
			u.id::text,
			u.email,
			u.display_name,
			u.status,
			u.created_at
		FROM app_core.sessions s
		JOIN app_core.users u ON u.id = s.user_id
		WHERE s.token_hash = $1
			AND s.revoked_at IS NULL
			AND s.expires_at > $2
			AND u.status = 'active'
	`, tokenHash, now).Scan(
		&session.ID,
		&session.CSRFToken,
		&session.CreatedAt,
		&session.LastSeenAt,
		&session.ExpiresAt,
		&session.User.ID,
		&session.User.Email,
		&session.User.DisplayName,
		&session.User.Status,
		&session.User.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return auth.Session{}, auth.ErrInvalidSession
	}
	return session, err
}

func (s *Store) TouchSession(
	ctx context.Context,
	sessionID string,
	now time.Time,
) error {
	_, err := s.pool.Exec(
		ctx,
		"UPDATE app_core.sessions SET last_seen_at=$2 WHERE id=$1",
		sessionID,
		now,
	)
	return err
}

func (s *Store) DeleteSession(
	ctx context.Context,
	tokenHash []byte,
) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE app_core.sessions
		SET revoked_at = NOW()
		WHERE token_hash = $1 AND revoked_at IS NULL
	`, tokenHash)
	return err
}

func (s *Store) RecordLoginAudit(
	ctx context.Context,
	audit auth.LoginAudit,
) error {
	var userID any
	if audit.UserID != "" {
		userID = audit.UserID
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO app_core.login_audit_logs
			(email, user_id, success, ip_address, user_agent, created_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`,
		audit.Email,
		userID,
		audit.Success,
		truncate(audit.IPAddress, 128),
		truncate(audit.UserAgent, 512),
		audit.CreatedAt,
	)
	return err
}

func truncate(value string, max int) string {
	if len(value) <= max {
		return value
	}
	return value[:max]
}
