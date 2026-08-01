package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/starslittle/agent/go-backend/internal/agentclient"
	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/conversation"
	"github.com/starslittle/agent/go-backend/internal/documents"
	runsupervisor "github.com/starslittle/agent/go-backend/internal/runs"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

type Server struct {
	handler       http.Handler
	runSupervisor *runsupervisor.Supervisor
}

type ProductServices struct {
	Documents *documents.Service
	Wiki      *wiki.Service
}

func New(
	cfg config.Config,
	logger *slog.Logger,
	authService *auth.Service,
	conversationServices ...*conversation.Service,
) (*Server, error) {
	return newServer(cfg, logger, authService, ProductServices{}, conversationServices...)
}

func NewWithProductServices(
	cfg config.Config,
	logger *slog.Logger,
	authService *auth.Service,
	productServices ProductServices,
	conversationServices ...*conversation.Service,
) (*Server, error) {
	return newServer(cfg, logger, authService, productServices, conversationServices...)
}

func newServer(
	cfg config.Config,
	logger *slog.Logger,
	authService *auth.Service,
	productServices ProductServices,
	conversationServices ...*conversation.Service,
) (*Server, error) {
	if authService == nil {
		return nil, errors.New("auth service is required")
	}
	proxy, err := newStreamProxy(
		cfg.PythonBaseURL,
		cfg.MaxRequestBytes,
		cfg.UpstreamHeaderTimeout,
		cfg.InternalAgentSecret,
		logger,
	)
	if err != nil {
		return nil, err
	}
	v1Client, err := agentclient.NewV1(
		cfg.PythonBaseURL,
		proxy.client,
		cfg.InternalAgentSecret,
	)
	if err != nil {
		return nil, err
	}
	mux := http.NewServeMux()
	authAPI := newAuthHTTP(cfg, authService)
	var runSupervisor *runsupervisor.Supervisor
	if len(conversationServices) > 0 && conversationServices[0] != nil {
		runSupervisor = runsupervisor.New(
			conversationServices[0],
			v1Client,
			logger,
			runsupervisor.Options{RunDeadline: cfg.AgentRunDeadline},
		)
	}
	if productServices.Documents != nil {
		spaceAPI := newSpaceHTTP(productServices.Documents, cfg.MaxRequestBytes)
		mux.Handle("GET /api/v1/space/entries", authAPI.requireSession(http.HandlerFunc(spaceAPI.list)))
		mux.Handle("GET /api/v1/space/folders/{folderID}", authAPI.requireSession(http.HandlerFunc(spaceAPI.folder)))
		mux.Handle("GET /api/v1/space/folders/{folderID}/breadcrumbs", authAPI.requireSession(http.HandlerFunc(spaceAPI.breadcrumbs)))
		mux.Handle("POST /api/v1/space/folders", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.createFolder)))))
		mux.Handle("PATCH /api/v1/space/folders/{folderID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.moveFolder)))))
		mux.Handle("DELETE /api/v1/space/folders/{folderID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.deleteFolder)))))
		mux.Handle("POST /api/v1/space/documents", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.createDocument)))))
		mux.Handle("GET /api/v1/space/documents/{documentID}", authAPI.requireSession(http.HandlerFunc(spaceAPI.document)))
		mux.Handle("PATCH /api/v1/space/documents/{documentID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.updateDocument)))))
		mux.Handle("PATCH /api/v1/space/documents/{documentID}/location", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.moveDocument)))))
		mux.Handle("DELETE /api/v1/space/documents/{documentID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(spaceAPI.deleteDocument)))))
		mux.Handle("GET /api/v1/space/documents/{documentID}/revisions", authAPI.requireSession(http.HandlerFunc(spaceAPI.revisions)))
	}
	if productServices.Wiki != nil {
		wikiAPI := newWikiHTTP(productServices.Wiki, cfg.MaxRequestBytes)
		mux.Handle("GET /api/v1/wiki-items", authAPI.requireSession(http.HandlerFunc(wikiAPI.list)))
		mux.Handle("POST /api/v1/wiki-items", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(wikiAPI.create)))))
		mux.Handle("GET /api/v1/wiki-items/{itemID}", authAPI.requireSession(http.HandlerFunc(wikiAPI.detail)))
		mux.Handle("PATCH /api/v1/wiki-items/{itemID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(wikiAPI.update)))))
		mux.Handle("POST /api/v1/wiki-items/{itemID}/{action}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(wikiAPI.changeStatus)))))
		mux.Handle("DELETE /api/v1/wiki-items/{itemID}", authAPI.protectMutation(authAPI.requireSession(authAPI.requireCSRF(http.HandlerFunc(wikiAPI.deletePermanently)))))
		mux.Handle("GET /api/v1/wiki-items/{itemID}/revisions", authAPI.requireSession(http.HandlerFunc(wikiAPI.revisions)))
	}

	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"status":  "ok",
			"service": "go-gateway",
		})
	})
	mux.HandleFunc("GET /readyz", readinessHandler(cfg.PythonBaseURL, proxy.client, authService))
	mux.Handle("POST /api/v1/auth/register", authAPI.protectMutation(http.HandlerFunc(authAPI.register)))
	mux.Handle("POST /api/v1/auth/login", authAPI.protectMutation(http.HandlerFunc(authAPI.login)))
	mux.HandleFunc("GET /api/v1/session", authAPI.session)
	mux.Handle("GET /api/v1/me", authAPI.requireSession(http.HandlerFunc(authAPI.me)))
	mux.Handle(
		"POST /api/v1/auth/logout",
		authAPI.protectMutation(
			authAPI.requireSession(
				authAPI.requireCSRF(http.HandlerFunc(authAPI.logout)),
			),
		),
	)
	mux.Handle(
		"POST /query_stream",
		authAPI.protectMutation(
			authAPI.requireSession(
				authAPI.requireCSRF(proxy),
			),
		),
	)
	if len(conversationServices) > 0 && conversationServices[0] != nil {
		observabilityAPI := newObservabilityHTTP(authService, conversationServices[0])
		conversationAPI := newConversationHTTP(
			conversationServices[0],
			proxy,
			v1Client,
			logger,
			cfg.MaxRequestBytes,
			cfg.AgentProtocolMode,
			cfg.AgentRunDeadline,
			cfg.AgentCancelTimeout,
			cfg.AgentReconcileTimeout,
			runSupervisor,
		)
		mux.Handle(
			"POST /api/v1/conversations",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.create)),
				),
			),
		)
		mux.Handle(
			"GET /api/v1/conversations",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.list)),
		)
		mux.Handle(
			"GET /api/v1/conversations/{conversationID}",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.get)),
		)
		mux.Handle(
			"PATCH /api/v1/conversations/{conversationID}",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.rename)),
				),
			),
		)
		mux.Handle(
			"DELETE /api/v1/conversations/{conversationID}",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.delete)),
				),
			),
		)
		mux.Handle(
			"GET /api/v1/conversations/{conversationID}/messages",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.messages)),
		)
		mux.Handle(
			"POST /api/v1/conversations/{conversationID}/runs",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.createRun)),
				),
			),
		)
		mux.Handle(
			"GET /api/v1/agent-runs",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.runs)),
		)
		mux.Handle(
			"GET /api/v1/agent-runs/{runID}",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.runDetail)),
		)
		mux.Handle(
			"GET /api/v1/internal/agent-runs",
			authAPI.requireSession(
				authAPI.requireObservabilityAdmin(
					http.HandlerFunc(observabilityAPI.runs),
				),
			),
		)
		mux.Handle(
			"GET /api/v1/internal/agent-runs/{runID}",
			authAPI.requireSession(
				authAPI.requireObservabilityAdmin(
					http.HandlerFunc(observabilityAPI.runDetail),
				),
			),
		)
		mux.Handle(
			"GET /api/v1/agent-runs/{runID}/events",
			authAPI.requireSession(http.HandlerFunc(conversationAPI.attachRunEvents)),
		)
		mux.Handle(
			"DELETE /api/v1/agent-runs/{runID}",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.cancelRun)),
				),
			),
		)
		mux.Handle(
			"POST /api/v1/conversations/{conversationID}/messages/stream",
			authAPI.protectMutation(
				authAPI.requireSession(
					authAPI.requireCSRF(http.HandlerFunc(conversationAPI.stream)),
				),
			),
		)
	}
	if cfg.StaticDir != "" {
		mux.Handle("/", spaHandler(cfg.StaticDir))
	}

	handler := recoveryMiddleware(
		logger,
		requestIDMiddleware(
			loggingMiddleware(logger, mux),
		),
	)
	return &Server{handler: handler, runSupervisor: runSupervisor}, nil
}

func (s *Server) Handler() http.Handler {
	return s.handler
}

func (s *Server) Start(ctx context.Context) error {
	if s.runSupervisor == nil {
		return nil
	}
	return s.runSupervisor.Start(ctx)
}

func (s *Server) Close(ctx context.Context) error {
	if s.runSupervisor == nil {
		return nil
	}
	return s.runSupervisor.Close(ctx)
}

func readinessHandler(
	pythonBaseURL string,
	client *http.Client,
	authService *auth.Service,
) http.HandlerFunc {
	healthURL := strings.TrimRight(pythonBaseURL, "/") + "/internal/ready"
	return func(w http.ResponseWriter, r *http.Request) {
		if err := authService.Ping(r.Context()); err != nil {
			writeJSONError(w, http.StatusServiceUnavailable, "database_not_ready")
			return
		}
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
