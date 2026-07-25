package auth

import (
	"context"
	"errors"
	"time"
)

var (
	ErrEmailExists        = errors.New("email already exists")
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrInvalidSession     = errors.New("invalid session")
	ErrRateLimited        = errors.New("too many login attempts")
)

type User struct {
	ID          string    `json:"id"`
	Email       string    `json:"email"`
	DisplayName string    `json:"display_name"`
	Status      string    `json:"status"`
	CreatedAt   time.Time `json:"created_at"`
}

type Credential struct {
	User         User
	PasswordHash string
}

type Session struct {
	ID         string
	User       User
	CSRFToken  string
	CreatedAt  time.Time
	LastSeenAt time.Time
	ExpiresAt  time.Time
}

type CreateUserParams struct {
	ID           string
	Email        string
	DisplayName  string
	PasswordHash string
}

type CreateSessionParams struct {
	ID        string
	UserID    string
	TokenHash []byte
	CSRFToken string
	UserAgent string
	ExpiresAt time.Time
}

type LoginAudit struct {
	Email     string
	UserID    string
	Success   bool
	IPAddress string
	UserAgent string
	CreatedAt time.Time
}

type Store interface {
	Ping(context.Context) error
	CreateUser(context.Context, CreateUserParams) (User, error)
	FindCredentialByEmail(context.Context, string) (Credential, error)
	CreateSession(context.Context, CreateSessionParams) error
	FindSession(context.Context, []byte, time.Time) (Session, error)
	TouchSession(context.Context, string, time.Time) error
	DeleteSession(context.Context, []byte) error
	RecordLoginAudit(context.Context, LoginAudit) error
}

type Result struct {
	User         User
	SessionToken string
	CSRFToken    string
	ExpiresAt    time.Time
}
