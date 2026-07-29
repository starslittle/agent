package config

import "testing"

func TestDatabaseURLFromEnvironmentUsesPostgresParts(t *testing.T) {
	t.Setenv("GO_DATABASE_URL", "")
	t.Setenv("DATABASE_URL", "")
	t.Setenv("POSTGRES_USER", "runtime_user")
	t.Setenv("POSTGRES_PASSWORD", "password with space")
	t.Setenv("POSTGRES_HOST", "postgres.internal")
	t.Setenv("POSTGRES_PORT", "5433")
	t.Setenv("POSTGRES_DB", "runtime_db")

	got := DatabaseURLFromEnvironment()
	want := "postgres://runtime_user:password%20with%20space@postgres.internal:5433/runtime_db"
	if got != want {
		t.Fatalf("DatabaseURLFromEnvironment() = %q, want %q", got, want)
	}
}

func TestLoadUsesPortAndPythonDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "")
	t.Setenv("ENVIRONMENT", "test")
	t.Setenv("HTTP_ADDR", "")
	t.Setenv("PORT", "9000")
	t.Setenv("PYTHON_BASE_URL", "")
	t.Setenv("MAX_REQUEST_BYTES", "")
	t.Setenv("UPSTREAM_HEADER_TIMEOUT", "")
	t.Setenv("SHUTDOWN_TIMEOUT", "")
	t.Setenv("SESSION_TTL", "")
	t.Setenv("COOKIE_SECURE", "")
	t.Setenv("GO_DATABASE_URL", "postgres://test:test@localhost/test")
	t.Setenv("INTERNAL_AGENT_SECRET", "test-secret-that-is-at-least-32-characters")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.HTTPAddr != ":9000" {
		t.Fatalf("HTTPAddr = %q, want :9000", cfg.HTTPAddr)
	}
	if cfg.AppEnv != "test" {
		t.Fatalf("AppEnv = %q, want test", cfg.AppEnv)
	}
	if cfg.PythonBaseURL != defaultPythonBaseURL {
		t.Fatalf("PythonBaseURL = %q", cfg.PythonBaseURL)
	}
}

func TestLoadPrefersGoEnvironmentAlias(t *testing.T) {
	t.Setenv("APP_ENV", "staging")
	t.Setenv("ENVIRONMENT", "production")
	t.Setenv("GO_DATABASE_URL", "postgres://test:test@localhost/test")
	t.Setenv("INTERNAL_AGENT_SECRET", "test-secret-that-is-at-least-32-characters")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.AppEnv != "staging" {
		t.Fatalf("AppEnv = %q, want staging", cfg.AppEnv)
	}
}

func TestLoadRejectsInvalidPythonURL(t *testing.T) {
	t.Setenv("GO_DATABASE_URL", "postgres://test:test@localhost/test")
	t.Setenv("INTERNAL_AGENT_SECRET", "test-secret-that-is-at-least-32-characters")
	t.Setenv("PYTHON_BASE_URL", "python:8000")

	if _, err := Load(); err == nil {
		t.Fatal("Load() expected an error")
	}
}
