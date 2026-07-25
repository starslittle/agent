package httpapi

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/config"
)

type Server struct {
	handler http.Handler
}

func New(cfg config.Config, logger *slog.Logger) (*Server, error) {
	proxy, err := newStreamProxy(
		cfg.PythonBaseURL,
		cfg.MaxRequestBytes,
		cfg.UpstreamHeaderTimeout,
		logger,
	)
	if err != nil {
		return nil, err
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  "ok",
			"service": "go-gateway",
		})
	})
	mux.HandleFunc("GET /readyz", readinessHandler(cfg.PythonBaseURL, proxy.client))
	mux.Handle("POST /query_stream", proxy)
	if cfg.StaticDir != "" {
		mux.Handle("/", spaHandler(cfg.StaticDir))
	}

	handler := recoveryMiddleware(
		logger,
		requestIDMiddleware(
			loggingMiddleware(logger, mux),
		),
	)
	return &Server{handler: handler}, nil
}

func (s *Server) Handler() http.Handler {
	return s.handler
}

func readinessHandler(pythonBaseURL string, client *http.Client) http.HandlerFunc {
	healthURL := strings.TrimRight(pythonBaseURL, "/") + "/healthz"
	return func(w http.ResponseWriter, r *http.Request) {
		request, err := http.NewRequestWithContext(r.Context(), http.MethodGet, healthURL, nil)
		if err != nil {
			writeJSONError(w, http.StatusServiceUnavailable, "python_upstream_not_ready")
			return
		}
		response, err := client.Do(request)
		if err != nil {
			writeJSONError(w, http.StatusServiceUnavailable, "python_upstream_not_ready")
			return
		}
		defer response.Body.Close()
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4<<10))
		if response.StatusCode != http.StatusOK {
			writeJSONError(w, http.StatusServiceUnavailable, "python_upstream_not_ready")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"status":   "ok",
			"service":  "go-gateway",
			"upstream": "python",
		})
	}
}

func spaHandler(staticDir string) http.Handler {
	fileServer := http.FileServer(http.Dir(staticDir))
	indexPath := filepath.Join(staticDir, "index.html")
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestPath := strings.TrimPrefix(filepath.Clean(r.URL.Path), string(filepath.Separator))
		if requestPath != "." {
			if info, err := os.Stat(filepath.Join(staticDir, requestPath)); err == nil && !info.IsDir() {
				fileServer.ServeHTTP(w, r)
				return
			}
		}
		http.ServeFile(w, r, indexPath)
	})
}

func writeJSONError(w http.ResponseWriter, status int, code string) {
	writeJSON(w, status, map[string]any{
		"error": code,
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
