package config

import (
	"fmt"
	"net"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	defaultPort                  = "8080"
	defaultPythonBaseURL         = "http://127.0.0.1:8000"
	defaultMaxRequestBytes int64 = 1 << 20
)

type Config struct {
	AppEnv                string
	HTTPAddr              string
	PythonBaseURL         string
	StaticDir             string
	DatabaseURL           string
	PublicOrigins         []string
	CookieSecure          bool
	SessionTTL            time.Duration
	InternalAgentSecret   string
	MaxRequestBytes       int64
	UpstreamHeaderTimeout time.Duration
	ShutdownTimeout       time.Duration
}

func Load() (Config, error) {
	appEnv := envOr("APP_ENV", envOr("ENVIRONMENT", "development"))
	cfg := Config{
		AppEnv:                appEnv,
		HTTPAddr:              httpAddr(),
		PythonBaseURL:         strings.TrimRight(envOr("PYTHON_BASE_URL", defaultPythonBaseURL), "/"),
		StaticDir:             strings.TrimSpace(os.Getenv("STATIC_DIR")),
		DatabaseURL:           databaseURL(),
		PublicOrigins:         csvValues(os.Getenv("PUBLIC_ORIGINS")),
		CookieSecure:          strings.EqualFold(appEnv, "production"),
		SessionTTL:            7 * 24 * time.Hour,
		InternalAgentSecret:   strings.TrimSpace(os.Getenv("INTERNAL_AGENT_SECRET")),
		MaxRequestBytes:       defaultMaxRequestBytes,
		UpstreamHeaderTimeout: 30 * time.Second,
		ShutdownTimeout:       10 * time.Second,
	}
	if len(cfg.PublicOrigins) == 0 && !strings.EqualFold(appEnv, "production") {
		cfg.PublicOrigins = []string{
			"http://localhost:5173",
			"http://127.0.0.1:5173",
			"http://localhost:8000",
			"http://127.0.0.1:8000",
		}
	}

	var err error
	if raw := strings.TrimSpace(os.Getenv("MAX_REQUEST_BYTES")); raw != "" {
		cfg.MaxRequestBytes, err = strconv.ParseInt(raw, 10, 64)
		if err != nil || cfg.MaxRequestBytes <= 0 {
			return Config{}, fmt.Errorf("MAX_REQUEST_BYTES must be a positive integer")
		}
	}

	if cfg.UpstreamHeaderTimeout, err = durationOr(
		"UPSTREAM_HEADER_TIMEOUT",
		cfg.UpstreamHeaderTimeout,
	); err != nil {
		return Config{}, err
	}

	if cfg.ShutdownTimeout, err = durationOr(
		"SHUTDOWN_TIMEOUT",
		cfg.ShutdownTimeout,
	); err != nil {
		return Config{}, err
	}

	if cfg.SessionTTL, err = durationOr("SESSION_TTL", cfg.SessionTTL); err != nil {
		return Config{}, err
	}

	if raw := strings.TrimSpace(os.Getenv("COOKIE_SECURE")); raw != "" {
		cfg.CookieSecure, err = strconv.ParseBool(raw)
		if err != nil {
			return Config{}, fmt.Errorf("COOKIE_SECURE must be true or false")
		}
	}

	if !strings.HasPrefix(cfg.PythonBaseURL, "http://") &&
		!strings.HasPrefix(cfg.PythonBaseURL, "https://") {
		return Config{}, fmt.Errorf("PYTHON_BASE_URL must use http or https")
	}
	if cfg.DatabaseURL == "" {
		return Config{}, fmt.Errorf("GO_DATABASE_URL or DATABASE_URL is required")
	}
	if len(cfg.InternalAgentSecret) < 32 {
		return Config{}, fmt.Errorf("INTERNAL_AGENT_SECRET must contain at least 32 characters")
	}
	if strings.EqualFold(cfg.AppEnv, "production") {
		if len(cfg.PublicOrigins) == 0 {
			return Config{}, fmt.Errorf("PUBLIC_ORIGINS is required in production")
		}
		if !cfg.CookieSecure {
			return Config{}, fmt.Errorf("COOKIE_SECURE must be true in production")
		}
	}

	return cfg, nil
}

func httpAddr() string {
	if addr := strings.TrimSpace(os.Getenv("HTTP_ADDR")); addr != "" {
		return addr
	}
	port := strings.TrimSpace(os.Getenv("PORT"))
	if port == "" {
		port = defaultPort
	}
	if strings.HasPrefix(port, ":") {
		return port
	}
	return ":" + port
}

func envOr(name, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(name)); value != "" {
		return value
	}
	return fallback
}

func databaseURL() string {
	if value := strings.TrimSpace(os.Getenv("GO_DATABASE_URL")); value != "" {
		return value
	}
	if value := strings.TrimSpace(os.Getenv("DATABASE_URL")); value != "" {
		return value
	}
	password := strings.TrimSpace(os.Getenv("POSTGRES_PASSWORD"))
	if password == "" {
		return ""
	}
	user := envOr("POSTGRES_USER", "qidian_agent")
	host := envOr("POSTGRES_HOST", "localhost")
	port := envOr("POSTGRES_PORT", "5432")
	database := envOr("POSTGRES_DB", "agent_db")
	return (&url.URL{
		Scheme: "postgres",
		User:   url.UserPassword(user, password),
		Host:   net.JoinHostPort(host, port),
		Path:   database,
	}).String()
}

func csvValues(raw string) []string {
	var values []string
	for _, value := range strings.Split(raw, ",") {
		value = strings.TrimRight(strings.TrimSpace(value), "/")
		if value != "" {
			values = append(values, value)
		}
	}
	return values
}

func durationOr(name string, fallback time.Duration) (time.Duration, error) {
	raw := strings.TrimSpace(os.Getenv(name))
	if raw == "" {
		return fallback, nil
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration", name)
	}
	return value, nil
}
