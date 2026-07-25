package config

import (
	"fmt"
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
	MaxRequestBytes       int64
	UpstreamHeaderTimeout time.Duration
	ShutdownTimeout       time.Duration
}

func Load() (Config, error) {
	cfg := Config{
		AppEnv:                envOr("APP_ENV", envOr("ENVIRONMENT", "development")),
		HTTPAddr:              httpAddr(),
		PythonBaseURL:         strings.TrimRight(envOr("PYTHON_BASE_URL", defaultPythonBaseURL), "/"),
		StaticDir:             strings.TrimSpace(os.Getenv("STATIC_DIR")),
		MaxRequestBytes:       defaultMaxRequestBytes,
		UpstreamHeaderTimeout: 30 * time.Second,
		ShutdownTimeout:       10 * time.Second,
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

	if !strings.HasPrefix(cfg.PythonBaseURL, "http://") &&
		!strings.HasPrefix(cfg.PythonBaseURL, "https://") {
		return Config{}, fmt.Errorf("PYTHON_BASE_URL must use http or https")
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
