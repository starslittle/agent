package main

import (
	"context"
	"log/slog"
	"os"
	"time"

	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/platform/postgres"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	databaseURL := config.DatabaseURLFromEnvironment()
	if databaseURL == "" {
		logger.Error(
			"invalid_configuration",
			"error",
			"GO_DATABASE_URL, DATABASE_URL, or POSTGRES_* is required",
		)
		os.Exit(1)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	store, err := postgres.Open(ctx, databaseURL)
	if err != nil {
		logger.Error("initialize_postgres", "error", err)
		os.Exit(1)
	}
	defer store.Close()

	if err := store.Migrate(ctx); err != nil {
		logger.Error("migrate_postgres", "error", err)
		os.Exit(1)
	}
	logger.Info("postgres_migrations_complete")
}
