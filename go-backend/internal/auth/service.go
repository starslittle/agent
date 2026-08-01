package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"net/mail"
	"strings"
	"time"
)

type Service struct {
	store      Store
	sessionTTL time.Duration
	limiter    *LoginLimiter
	now        func() time.Time
	dummyHash  string
}

func NewService(store Store, sessionTTL time.Duration) *Service {
	dummyHash, err := HashPassword("qidian-dummy-password-for-timing-equalization")
	if err != nil {
		panic(fmt.Sprintf("create dummy password hash: %v", err))
	}
	return &Service{
		store:      store,
		sessionTTL: sessionTTL,
		limiter:    NewLoginLimiter(6, 15*time.Minute),
		now:        time.Now,
		dummyHash:  dummyHash,
	}
}

func (s *Service) Register(
	ctx context.Context,
	email string,
	password string,
	displayName string,
	userAgent string,
) (Result, error) {
	email, err := normalizeEmail(email)
	if err != nil {
		return Result{}, err
	}
	displayName = strings.TrimSpace(displayName)
	if displayName == "" {
		displayName = strings.Split(email, "@")[0]
	}
	if len([]rune(displayName)) > 80 {
		return Result{}, errors.New("display name is too long")
	}
	passwordHash, err := HashPassword(password)
	if err != nil {
		return Result{}, err
	}
	user, err := s.store.CreateUser(ctx, CreateUserParams{
		ID:           NewID(),
		Email:        email,
		DisplayName:  displayName,
		PasswordHash: passwordHash,
	})
	if err != nil {
		return Result{}, err
	}
	return s.newSession(ctx, user, userAgent)
}

func (s *Service) Login(
	ctx context.Context,
	email string,
	password string,
	userAgent string,
	ipAddress string,
) (Result, error) {
	normalizedEmail, err := normalizeEmail(email)
	if err != nil {
		normalizedEmail = strings.ToLower(strings.TrimSpace(email))
	}
	emailLimitKey := "email:" + normalizedEmail
	ipLimitKey := "ip:" + ipAddress
	if !s.limiter.Allow(emailLimitKey, s.now()) ||
		!s.limiter.Allow(ipLimitKey, s.now()) {
		return Result{}, ErrRateLimited
	}

	credential, findErr := s.store.FindCredentialByEmail(ctx, normalizedEmail)
	hashToCheck := credential.PasswordHash
	if findErr != nil {
		hashToCheck = s.dummyHash
	}
	valid := VerifyPassword(hashToCheck, password) && findErr == nil
	audit := LoginAudit{
		Email:     normalizedEmail,
		Success:   valid,
		IPAddress: ipAddress,
		UserAgent: userAgent,
		CreatedAt: s.now().UTC(),
	}
	if valid {
		audit.UserID = credential.User.ID
		s.limiter.Reset(emailLimitKey)
		s.limiter.Reset(ipLimitKey)
	}
	_ = s.store.RecordLoginAudit(ctx, audit)

	if !valid {
		return Result{}, ErrInvalidCredentials
	}
	if credential.User.Status != "active" {
		return Result{}, ErrInvalidCredentials
	}
	return s.newSession(ctx, credential.User, userAgent)
}

func (s *Service) Authenticate(
	ctx context.Context,
	sessionToken string,
) (Session, error) {
	tokenHash := hashToken(sessionToken)
	if len(tokenHash) == 0 {
		return Session{}, ErrInvalidSession
	}
	session, err := s.store.FindSession(ctx, tokenHash, s.now().UTC())
	if err != nil {
		return Session{}, ErrInvalidSession
	}
	if s.now().Sub(session.LastSeenAt) >= 5*time.Minute {
		_ = s.store.TouchSession(ctx, session.ID, s.now().UTC())
	}
	return session, nil
}

func (s *Service) ValidateCSRF(session Session, token string) bool {
	return token != "" &&
		subtle.ConstantTimeCompare(
			[]byte(token),
			[]byte(session.CSRFToken),
		) == 1
}

func (s *Service) Logout(ctx context.Context, sessionToken string) error {
	hash := hashToken(sessionToken)
	if len(hash) == 0 {
		return nil
	}
	return s.store.DeleteSession(ctx, hash)
}

func (s *Service) Ping(ctx context.Context) error {
	return s.store.Ping(ctx)
}

func (s *Service) RecordObservabilityAccess(
	ctx context.Context,
	audit ObservabilityAccessAudit,
) error {
	if audit.ActorUserID == "" ||
		(audit.Action != "agent_runs.list" && audit.Action != "agent_runs.detail") {
		return errors.New("invalid observability access audit")
	}
	audit.CreatedAt = s.now().UTC()
	return s.store.RecordObservabilityAccess(ctx, audit)
}

func (s *Service) newSession(
	ctx context.Context,
	user User,
	userAgent string,
) (Result, error) {
	sessionToken, err := randomToken()
	if err != nil {
		return Result{}, err
	}
	csrfToken, err := randomToken()
	if err != nil {
		return Result{}, err
	}
	now := s.now().UTC()
	expiresAt := now.Add(s.sessionTTL)
	if err := s.store.CreateSession(ctx, CreateSessionParams{
		ID:        NewID(),
		UserID:    user.ID,
		TokenHash: hashToken(sessionToken),
		CSRFToken: csrfToken,
		UserAgent: truncate(userAgent, 512),
		ExpiresAt: expiresAt,
	}); err != nil {
		return Result{}, err
	}
	return Result{
		User:         user,
		SessionToken: sessionToken,
		CSRFToken:    csrfToken,
		ExpiresAt:    expiresAt,
	}, nil
}

func normalizeEmail(raw string) (string, error) {
	value := strings.ToLower(strings.TrimSpace(raw))
	if len(value) == 0 || len(value) > 254 {
		return "", errors.New("invalid email address")
	}
	address, err := mail.ParseAddress(value)
	if err != nil || address.Address != value || !strings.Contains(value, "@") {
		return "", errors.New("invalid email address")
	}
	return value, nil
}

func randomToken() (string, error) {
	value := make([]byte, 32)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("generate secure token: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(value), nil
}

func NewID() string {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		panic("crypto/rand unavailable")
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4],
		value[4:6],
		value[6:8],
		value[8:10],
		value[10:16],
	)
}

func hashToken(token string) []byte {
	token = strings.TrimSpace(token)
	if token == "" {
		return nil
	}
	hash := sha256.Sum256([]byte(token))
	return hash[:]
}

func truncate(value string, max int) string {
	if len(value) <= max {
		return value
	}
	return value[:max]
}
