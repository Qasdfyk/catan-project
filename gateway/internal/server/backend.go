package server

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

// Backend is the rules server. It owns all game state and decisions.
type Backend interface {
	Session(ctx context.Context, roomID, token string) (Session, error)
	Action(ctx context.Context, roomID, token, action string, payload json.RawMessage) error
}

type Session struct {
	Seat    int             `json:"seat"`
	Public  json.RawMessage `json:"public"`
	Private json.RawMessage `json:"private"`
}

// RejectedError is a refusal with a message meant for the player.
type RejectedError struct {
	Status  int
	Message string
}

func (e *RejectedError) Error() string { return e.Message }

// IsSessionFatal reports refusals that retrying on this connection cannot fix.
func IsSessionFatal(err error) bool {
	var rejected *RejectedError
	if !errors.As(err, &rejected) {
		return false
	}
	return rejected.Status == http.StatusUnauthorized || rejected.Status == http.StatusNotFound
}

type HTTPBackend struct {
	baseURL string
	apiKey  string
	client  *http.Client
}

func NewHTTPBackend(baseURL, apiKey string) *HTTPBackend {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.MaxIdleConnsPerHost = 64
	return &HTTPBackend{
		baseURL: baseURL,
		apiKey:  apiKey,
		client:  &http.Client{Timeout: 10 * time.Second, Transport: transport},
	}
}

func (b *HTTPBackend) Session(ctx context.Context, roomID, token string) (Session, error) {
	var session Session
	err := b.post(ctx, roomID, "session", map[string]any{"token": token}, &session)
	return session, err
}

func (b *HTTPBackend) Action(ctx context.Context, roomID, token, action string, payload json.RawMessage) error {
	if len(payload) == 0 || string(payload) == "null" {
		payload = json.RawMessage("{}")
	}
	body := map[string]any{"token": token, "type": action, "payload": payload}
	return b.post(ctx, roomID, "actions", body, nil)
}

// Timeout asks the backend to end a turn whose time ran out. Calling it before
// the deadline does nothing, so it is safe to repeat.
func (b *HTTPBackend) Timeout(ctx context.Context, roomID string) error {
	return b.post(ctx, roomID, "timeout", nil, nil)
}

func (b *HTTPBackend) post(ctx context.Context, roomID, path string, body any, out any) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(encoded)
	}
	target := fmt.Sprintf("%s/internal/rooms/%s/%s", b.baseURL, url.PathEscape(roomID), path)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, target, reader)
	if err != nil {
		return err
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	request.Header.Set("X-Internal-Key", b.apiKey)

	response, err := b.client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	if response.StatusCode >= 500 {
		return fmt.Errorf("backend returned %d", response.StatusCode)
	}
	if response.StatusCode >= 400 {
		var refusal struct {
			Detail string `json:"detail"`
		}
		if err := json.NewDecoder(response.Body).Decode(&refusal); err != nil {
			return fmt.Errorf("backend returned %d", response.StatusCode)
		}
		return &RejectedError{Status: response.StatusCode, Message: refusal.Detail}
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(response.Body).Decode(out)
}
