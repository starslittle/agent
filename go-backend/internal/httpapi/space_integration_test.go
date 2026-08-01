package httpapi

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/starslittle/agent/go-backend/internal/auth"
	"github.com/starslittle/agent/go-backend/internal/config"
	"github.com/starslittle/agent/go-backend/internal/documents"
	"github.com/starslittle/agent/go-backend/internal/platform/postgres"
	"github.com/starslittle/agent/go-backend/internal/wiki"
)

func TestPersonalSpaceHTTPIntegration(t *testing.T) {
	databaseURL := os.Getenv("TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("TEST_DATABASE_URL is not configured")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	store, err := postgres.Open(ctx, databaseURL)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer store.Close()
	if err := store.Migrate(ctx); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	cfg := config.Config{
		AppEnv: "test", PythonBaseURL: "http://127.0.0.1:1", MaxRequestBytes: 1 << 20,
		UpstreamHeaderTimeout: time.Second, SessionTTL: time.Hour,
		InternalAgentSecret: "test-secret-that-is-at-least-32-characters",
	}
	server, err := NewWithProductServices(
		cfg,
		slog.New(slog.NewTextHandler(io.Discard, nil)),
		auth.NewService(store, time.Hour),
		ProductServices{Documents: documents.NewService(store, documents.DefaultLimits()), Wiki: wiki.NewService(store)},
	)
	if err != nil {
		t.Fatalf("NewWithProductServices() error = %v", err)
	}

	unauthorized := httptest.NewRecorder()
	server.Handler().ServeHTTP(unauthorized, httptest.NewRequest(http.MethodGet, "/api/v1/space/entries", nil))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized list status = %d", unauthorized.Code)
	}

	cookie, csrf := registerIntegrationUser(t, server)
	noCSRF := authenticatedRequest(http.MethodPost, "/api/v1/space/folders", `{"parent_id":null,"name":"拒绝"}`, cookie, "")
	noCSRFResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(noCSRFResponse, noCSRF)
	if noCSRFResponse.Code != http.StatusForbidden {
		t.Fatalf("missing CSRF status = %d", noCSRFResponse.Code)
	}

	root := createSpaceFolderHTTP(t, server, cookie, csrf, nil, "求职")
	nested := createSpaceFolderHTTP(t, server, cookie, csrf, &root.ID, "面试")
	importContent := "# 导入文档\n"
	importHash := sha256.Sum256([]byte(importContent))
	importManifest := documents.ImportManifest{
		BatchID:        "11111111-1111-4111-8111-111111111111",
		TargetFolderID: &root.ID,
		RootName:       documentStringPointer("资料库"),
		Entries:        []documents.ImportEntry{{Kind: "file", RelativePath: "嵌套/说明.md", Size: int64(len(importContent)), ContentHash: fmt.Sprintf("%x", importHash), MediaType: "text/markdown", UploadField: "file_0"}},
	}
	preflightBody, _ := json.Marshal(importManifest)
	preflightRequest := authenticatedRequest(http.MethodPost, "/api/v1/space/imports:preflight", string(preflightBody), cookie, csrf)
	preflightResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(preflightResponse, preflightRequest)
	if preflightResponse.Code != http.StatusOK {
		t.Fatalf("import preflight status = %d: %s", preflightResponse.Code, preflightResponse.Body.String())
	}
	var upload bytes.Buffer
	multipartWriter := multipart.NewWriter(&upload)
	manifestPart, _ := multipartWriter.CreateFormField("manifest")
	_, _ = manifestPart.Write(preflightBody)
	filePart, _ := multipartWriter.CreateFormFile("file_0", "说明.md")
	_, _ = filePart.Write([]byte(importContent))
	_ = multipartWriter.Close()
	importRequest := httptest.NewRequest(http.MethodPost, "/api/v1/space/imports", &upload)
	importRequest.AddCookie(cookie)
	importRequest.Header.Set("Content-Type", multipartWriter.FormDataContentType())
	importRequest.Header.Set("X-CSRF-Token", csrf)
	importRequest.Header.Set("Idempotency-Key", "space-http-import")
	importResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(importResponse, importRequest)
	if importResponse.Code != http.StatusOK {
		t.Fatalf("import status = %d: %s", importResponse.Code, importResponse.Body.String())
	}
	var importResult documents.ImportResult
	decodeHTTPJSON(t, importResponse, &importResult)
	if importResult.Added != 1 || importResult.RootFolderID == nil {
		t.Fatalf("import result = %#v", importResult)
	}
	conflict := authenticatedRequest(http.MethodPost, "/api/v1/space/folders", `{"parent_id":null,"name":" 求职 "}`, cookie, csrf)
	conflict.Header.Set("Idempotency-Key", auth.NewID())
	conflictResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(conflictResponse, conflict)
	if conflictResponse.Code != http.StatusConflict {
		t.Fatalf("name conflict status = %d: %s", conflictResponse.Code, conflictResponse.Body.String())
	}

	documentBody, _ := json.Marshal(map[string]any{"folder_id": nested.ID, "name": "目标.md", "content": "# 第一版", "source": "manual"})
	documentRequest := authenticatedRequest(http.MethodPost, "/api/v1/space/documents", string(documentBody), cookie, csrf)
	documentKey := auth.NewID()
	documentRequest.Header.Set("Idempotency-Key", documentKey)
	documentResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(documentResponse, documentRequest)
	if documentResponse.Code != http.StatusCreated {
		t.Fatalf("create document status = %d: %s", documentResponse.Code, documentResponse.Body.String())
	}
	var document documents.Document
	decodeHTTPJSON(t, documentResponse, &document)
	replayDocument := authenticatedRequest(http.MethodPost, "/api/v1/space/documents", string(documentBody), cookie, csrf)
	replayDocument.Header.Set("Idempotency-Key", documentKey)
	replayDocumentResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(replayDocumentResponse, replayDocument)
	var replayed documents.Document
	decodeHTTPJSON(t, replayDocumentResponse, &replayed)
	if replayDocumentResponse.Code != http.StatusCreated || replayed.ID != document.ID {
		t.Fatalf("idempotent document replay status=%d id=%s", replayDocumentResponse.Code, replayed.ID)
	}

	updateBody, _ := json.Marshal(map[string]any{"content": "# 第二版", "expected_version": document.Version})
	updateRequest := authenticatedRequest(http.MethodPatch, "/api/v1/space/documents/"+document.ID, string(updateBody), cookie, csrf)
	updateResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(updateResponse, updateRequest)
	if updateResponse.Code != http.StatusOK {
		t.Fatalf("update document status = %d: %s", updateResponse.Code, updateResponse.Body.String())
	}
	var updated documents.Document
	decodeHTTPJSON(t, updateResponse, &updated)
	staleRequest := authenticatedRequest(http.MethodPatch, "/api/v1/space/documents/"+document.ID, string(updateBody), cookie, csrf)
	staleResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(staleResponse, staleRequest)
	if staleResponse.Code != http.StatusConflict {
		t.Fatalf("stale update status = %d", staleResponse.Code)
	}

	wikiBody, _ := json.Marshal(map[string]any{
		"type": "current_state", "domain": "career", "status": "confirmed", "content": "正在准备秋招",
		"source_type": "document_extracted", "document_id": document.ID, "document_revision_id": updated.CurrentRevisionID,
	})
	wikiRequest := authenticatedRequest(http.MethodPost, "/api/v1/wiki-items", string(wikiBody), cookie, csrf)
	wikiRequest.Header.Set("Idempotency-Key", auth.NewID())
	wikiResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(wikiResponse, wikiRequest)
	if wikiResponse.Code != http.StatusCreated {
		t.Fatalf("create wiki status = %d: %s", wikiResponse.Code, wikiResponse.Body.String())
	}
	var wikiDetail wiki.ItemDetail
	decodeHTTPJSON(t, wikiResponse, &wikiDetail)

	listWiki := authenticatedRequest(http.MethodGet, "/api/v1/wiki-items?document_id="+document.ID, "", cookie, "")
	listWikiResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(listWikiResponse, listWiki)
	if listWikiResponse.Code != http.StatusOK || !strings.Contains(listWikiResponse.Body.String(), wikiDetail.Item.ID) {
		t.Fatalf("list wiki status = %d: %s", listWikiResponse.Code, listWikiResponse.Body.String())
	}

	otherCookie, _ := registerIntegrationUser(t, server)
	crossUser := authenticatedRequest(http.MethodGet, "/api/v1/space/documents/"+document.ID, "", otherCookie, "")
	crossUserResponse := httptest.NewRecorder()
	server.Handler().ServeHTTP(crossUserResponse, crossUser)
	if crossUserResponse.Code != http.StatusNotFound {
		t.Fatalf("cross-user document status = %d", crossUserResponse.Code)
	}

	if cacheControl := listWikiResponse.Header().Get("Cache-Control"); cacheControl != "no-store" {
		t.Fatalf("private response Cache-Control = %q", cacheControl)
	}
}

func documentStringPointer(value string) *string { return &value }

func createSpaceFolderHTTP(t *testing.T, server *Server, cookie *http.Cookie, csrf string, parentID *string, name string) documents.Folder {
	t.Helper()
	body, _ := json.Marshal(map[string]any{"parent_id": parentID, "name": name})
	request := authenticatedRequest(http.MethodPost, "/api/v1/space/folders", string(body), cookie, csrf)
	request.Header.Set("Idempotency-Key", auth.NewID())
	response := httptest.NewRecorder()
	server.Handler().ServeHTTP(response, request)
	if response.Code != http.StatusCreated {
		t.Fatalf("create folder status = %d: %s", response.Code, response.Body.String())
	}
	var folder documents.Folder
	decodeHTTPJSON(t, response, &folder)
	return folder
}

func decodeHTTPJSON(t *testing.T, response *httptest.ResponseRecorder, target any) {
	t.Helper()
	if err := json.Unmarshal(response.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response: %v", err)
	}
}
