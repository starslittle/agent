package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/httpapi"
	"github.com/starslittle/agent/go-backend/internal/platform/postgres"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	cfg, err := config.Load()
	if err != nil {
		logger.Error("invalid_configuration", "error", err)
		os.Exit(1)
	}

	startupCtx, startupCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer startupCancel()
	store, err := postgres.Open(startupCtx, cfg.DatabaseURL)
	if err != nil {
		logger.Error("initialize_postgres", "error", err)
		os.Exit(1)
	}
	defer store.Close()
	if err := store.Migrate(startupCtx); err != nil {
		logger.Error("migrate_postgres", "error", err)
		os.Exit(1)
	}

	authService := auth.NewService(store, cfg.SessionTTL)
	api, err := httpapi.New(cfg, logger, authService)
	if err != nil {
		logger.Error("initialize_server", "error", err)
		os.Exit(1)
	}

	server := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           api.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       90 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownTimeout)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("shutdown_server", "error", err)
		}
	}()

	logger.Info(
		"go_gateway_started",
		"app_env", cfg.AppEnv,
		"http_addr", cfg.HTTPAddr,
		"python_base_url", cfg.PythonBaseURL,
	)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Error("serve_http", "error", err)
		os.Exit(1)
	}
}
