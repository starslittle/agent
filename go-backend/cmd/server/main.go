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

	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/httpapi"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	cfg, err := config.Load()
	if err != nil {
		logger.Error("invalid_configuration", "error", err)
		os.Exit(1)
	}

	api, err := httpapi.New(cfg, logger)
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
