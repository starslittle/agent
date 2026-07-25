package config

import "testing"

func TestLoadUsesPortAndPythonDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "")
	t.Setenv("ENVIRONMENT", "test")
	t.Setenv("HTTP_ADDR", "")
	t.Setenv("PORT", "9000")
	t.Setenv("PYTHON_BASE_URL", "")
	t.Setenv("MAX_REQUEST_BYTES", "")
	t.Setenv("UPSTREAM_HEADER_TIMEOUT", "")
	t.Setenv("SHUTDOWN_TIMEOUT", "")

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

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.AppEnv != "staging" {
		t.Fatalf("AppEnv = %q, want staging", cfg.AppEnv)
	}
}

func TestLoadRejectsInvalidPythonURL(t *testing.T) {
	t.Setenv("PYTHON_BASE_URL", "python:8000")

	if _, err := Load(); err == nil {
		t.Fatal("Load() expected an error")
	}
}
