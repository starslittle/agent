package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
)

type sessionContextKey struct{}

type authHTTP struct {
	service       *auth.Service
	cookieName    string
	cookieSecure  bool
	publicOrigins map[string]struct{}
	production    bool
}

func newAuthHTTP(cfg config.Config, service *auth.Service) *authHTTP {
	origins := make(map[string]struct{}, len(cfg.PublicOrigins))
	for _, origin := range cfg.PublicOrigins {
		origins[origin] = struct{}{}
	}
	cookieName := "qidian_session"
	if cfg.CookieSecure {
		cookieName = "__Host-qidian_session"
	}
	return &authHTTP{
		service:       service,
		cookieName:    cookieName,
		cookieSecure:  cfg.CookieSecure,
		publicOrigins: origins,
		production:    strings.EqualFold(cfg.AppEnv, "production"),
	}
}

func (a *authHTTP) register(w http.ResponseWriter, r *http.Request) {
	setAuthResponseHeaders(w)
	var request struct {
		Email       string `json:"email"`
		Password    string `json:"password"`
		DisplayName string `json:"display_name"`
	}
	if err := decodeJSONBody(r, &request, 32<<10); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_request")
		return
	}
	result, err := a.service.Register(
		r.Context(),
		request.Email,
		request.Password,
		request.DisplayName,
		r.UserAgent(),
	)
	if err != nil {
		if errors.Is(err, auth.ErrEmailExists) {
			writeJSONError(w, http.StatusConflict, "email_already_registered")
			return
		}
		writeJSON(w, http.StatusBadRequest, map[string]any{
			"error":   "registration_failed",
			"message": err.Error(),
		})
		return
	}
	a.setSessionCookie(w, result)
	writeAuthResult(w, http.StatusCreated, result)
}

func (a *authHTTP) login(w http.ResponseWriter, r *http.Request) {
	setAuthResponseHeaders(w)
	var request struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := decodeJSONBody(r, &request, 16<<10); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid_request")
		return
	}
	result, err := a.service.Login(
		r.Context(),
		request.Email,
		request.Password,
		r.UserAgent(),
		clientIPAddress(r),
	)
	if err != nil {
		if errors.Is(err, auth.ErrRateLimited) {
			w.Header().Set("Retry-After", "900")
			writeJSONError(w, http.StatusTooManyRequests, "too_many_attempts")
			return
		}
		writeJSONError(w, http.StatusUnauthorized, "invalid_credentials")
		return
	}
	a.setSessionCookie(w, result)
	writeAuthResult(w, http.StatusOK, result)
}

func (a *authHTTP) logout(w http.ResponseWriter, r *http.Request) {
	setAuthResponseHeaders(w)
	cookie, _ := r.Cookie(a.cookieName)
	if cookie != nil {
		_ = a.service.Logout(r.Context(), cookie.Value)
	}
	a.clearSessionCookie(w)
	w.WriteHeader(http.StatusNoContent)
}

func (a *authHTTP) session(w http.ResponseWriter, r *http.Request) {
	setAuthResponseHeaders(w)
	cookie, err := r.Cookie(a.cookieName)
	if err != nil || cookie.Value == "" {
		writeJSON(w, http.StatusOK, map[string]any{"authenticated": false})
		return
	}
	session, err := a.service.Authenticate(r.Context(), cookie.Value)
	if err != nil {
		a.clearSessionCookie(w)
		writeJSON(w, http.StatusOK, map[string]any{"authenticated": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"authenticated": true,
		"user":          session.User,
		"csrf_token":    session.CSRFToken,
		"expires_at":    session.ExpiresAt,
	})
}

func (a *authHTTP) me(w http.ResponseWriter, r *http.Request) {
	setAuthResponseHeaders(w)
	session, ok := sessionFromContext(r.Context())
	if !ok {
		writeJSONError(w, http.StatusUnauthorized, "authentication_required")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"user": session.User})
}

func setAuthResponseHeaders(w http.ResponseWriter) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Pragma", "no-cache")
}

func (a *authHTTP) requireSession(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cookie, err := r.Cookie(a.cookieName)
		if err != nil || cookie.Value == "" {
			writeJSONError(w, http.StatusUnauthorized, "authentication_required")
			return
		}
		session, err := a.service.Authenticate(r.Context(), cookie.Value)
		if err != nil {
			a.clearSessionCookie(w)
			writeJSONError(w, http.StatusUnauthorized, "authentication_required")
			return
		}
		ctx := context.WithValue(r.Context(), sessionContextKey{}, session)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (a *authHTTP) requireCSRF(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		session, ok := sessionFromContext(r.Context())
		if !ok || !a.service.ValidateCSRF(session, r.Header.Get("X-CSRF-Token")) {
			writeJSONError(w, http.StatusForbidden, "invalid_csrf_token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (a *authHTTP) protectMutation(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.EqualFold(r.Header.Get("Sec-Fetch-Site"), "cross-site") {
			writeJSONError(w, http.StatusForbidden, "cross_site_request_blocked")
			return
		}
		origin := strings.TrimRight(strings.TrimSpace(r.Header.Get("Origin")), "/")
		if origin == "" {
			if a.production {
				writeJSONError(w, http.StatusForbidden, "origin_required")
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		if _, allowed := a.publicOrigins[origin]; !allowed {
			writeJSONError(w, http.StatusForbidden, "origin_not_allowed")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (a *authHTTP) setSessionCookie(w http.ResponseWriter, result auth.Result) {
	maxAge := int(time.Until(result.ExpiresAt).Seconds())
	http.SetCookie(w, &http.Cookie{
		Name:     a.cookieName,
		Value:    result.SessionToken,
		Path:     "/",
		MaxAge:   maxAge,
		Expires:  result.ExpiresAt,
		HttpOnly: true,
		Secure:   a.cookieSecure,
		SameSite: http.SameSiteLaxMode,
	})
}

func (a *authHTTP) clearSessionCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     a.cookieName,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		Expires:  time.Unix(1, 0),
		HttpOnly: true,
		Secure:   a.cookieSecure,
		SameSite: http.SameSiteLaxMode,
	})
}

func writeAuthResult(w http.ResponseWriter, status int, result auth.Result) {
	writeJSON(w, status, map[string]any{
		"authenticated": true,
		"user":          result.User,
		"csrf_token":    result.CSRFToken,
		"expires_at":    result.ExpiresAt,
	})
}

func sessionFromContext(ctx context.Context) (auth.Session, bool) {
	session, ok := ctx.Value(sessionContextKey{}).(auth.Session)
	return session, ok
}

func decodeJSONBody(r *http.Request, target any, limit int64) error {
	defer r.Body.Close()
	body, err := io.ReadAll(io.LimitReader(r.Body, limit+1))
	if err != nil {
		return err
	}
	if int64(len(body)) > limit {
		return errors.New("request body too large")
	}
	decoder := json.NewDecoder(strings.NewReader(string(body)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var extra any
	if decoder.Decode(&extra) == nil {
		return errors.New("multiple JSON values")
	}
	return nil
}

func clientIPAddress(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}
