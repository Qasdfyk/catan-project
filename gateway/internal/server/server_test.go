package server

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"
)

type fakeBackend struct {
	mu      sync.Mutex
	seats   map[string]int
	actions []string
	reject  error
}

func (b *fakeBackend) Session(_ context.Context, roomID, token string) (Session, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	seat, ok := b.seats[token]
	if !ok {
		return Session{}, &RejectedError{Status: http.StatusUnauthorized, Message: "bad session"}
	}
	return Session{
		Seat:    seat,
		Public:  json.RawMessage(`{"version":1}`),
		Private: json.RawMessage(`{"seat":` + seatKey(seat) + `}`),
	}, nil
}

func (b *fakeBackend) Action(_ context.Context, _, token, action string, _ json.RawMessage) error {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.actions = append(b.actions, token+":"+action)
	return b.reject
}

type fakePresence struct {
	mu      sync.Mutex
	marked  map[string]bool
	cleared chan string
}

func newFakePresence() *fakePresence {
	return &fakePresence{marked: map[string]bool{}, cleared: make(chan string, 16)}
}

func (p *fakePresence) Mark(_ context.Context, roomID string, seats []int) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, seat := range seats {
		p.marked[presenceKey(roomID, seat)] = true
	}
	return nil
}

func (p *fakePresence) Clear(_ context.Context, roomID string, seat int) error {
	p.cleared <- presenceKey(roomID, seat)
	return nil
}

type harness struct {
	url      string
	hub      *Hub
	backend  *fakeBackend
	presence *fakePresence
}

func newHarness(t *testing.T) *harness {
	t.Helper()
	backend := &fakeBackend{seats: map[string]int{"alice": 0, "bob": 1}}
	presence := newFakePresence()
	hub := NewHub(presence)
	server := httptest.NewServer(&Handler{Hub: hub, Backend: backend, OriginPatterns: []string{"allowed.test"}})
	t.Cleanup(server.Close)
	return &harness{"ws" + strings.TrimPrefix(server.URL, "http"), hub, backend, presence}
}

type testConn struct {
	t    *testing.T
	conn *websocket.Conn
}

func (h *harness) dial(t *testing.T) *testConn {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	conn, _, err := websocket.Dial(ctx, h.url, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { conn.CloseNow() })
	return &testConn{t, conn}
}

func (c *testConn) send(message map[string]any) {
	c.t.Helper()
	data, _ := json.Marshal(message)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if err := c.conn.Write(ctx, websocket.MessageText, data); err != nil {
		c.t.Fatal(err)
	}
}

func (c *testConn) read() map[string]any {
	c.t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_, data, err := c.conn.Read(ctx)
	if err != nil {
		c.t.Fatal(err)
	}
	var message map[string]any
	if err := json.Unmarshal(data, &message); err != nil {
		c.t.Fatal(err)
	}
	return message
}

// readType skips messages of other types, such as presence updates.
func (c *testConn) readType(kind string) map[string]any {
	c.t.Helper()
	for {
		if message := c.read(); message["type"] == kind {
			return message
		}
	}
}

func (h *harness) join(t *testing.T, token string) *testConn {
	t.Helper()
	conn := h.dial(t)
	conn.send(map[string]any{"type": "hello", "room_id": "room", "token": token})
	conn.readType("state")
	return conn
}

func TestHelloReturnsStateOfTheSeat(t *testing.T) {
	h := newHarness(t)
	conn := h.dial(t)

	conn.send(map[string]any{"type": "hello", "room_id": "room", "token": "bob"})

	state := conn.readType("state")
	if state["private"].(map[string]any)["seat"] != float64(1) {
		t.Fatalf("wrong private part: %v", state)
	}
}

func TestInvalidTokenClosesTheConnection(t *testing.T) {
	h := newHarness(t)
	conn := h.dial(t)

	conn.send(map[string]any{"type": "hello", "room_id": "room", "token": "forged"})

	message := conn.readType("error")
	if message["fatal"] != true || message["message"] != "bad session" {
		t.Fatalf("unexpected error: %v", message)
	}
}

func TestFirstMessageMustBeHello(t *testing.T) {
	h := newHarness(t)
	conn := h.dial(t)

	conn.send(map[string]any{"type": "action", "action": "roll_dice"})

	if message := conn.readType("error"); message["fatal"] != true {
		t.Fatalf("unexpected error: %v", message)
	}
	if len(h.backend.actions) != 0 {
		t.Fatalf("action reached backend before authentication: %v", h.backend.actions)
	}
}

func TestEventsCarryOnlyTheOwnPrivatePart(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	bob := h.join(t, "bob")

	h.hub.Deliver(RoomEvent{
		RoomID: "room",
		Public: json.RawMessage(`{"version":2}`),
		Private: map[string]json.RawMessage{
			"0": json.RawMessage(`{"secret":"alice-hand"}`),
			"1": json.RawMessage(`{"secret":"bob-hand"}`),
		},
	})

	if got := alice.readType("state")["private"].(map[string]any)["secret"]; got != "alice-hand" {
		t.Fatalf("alice got %v", got)
	}
	if got := bob.readType("state")["private"].(map[string]any)["secret"]; got != "bob-hand" {
		t.Fatalf("bob got %v", got)
	}
}

func TestEventsStayInsideTheRoom(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")

	h.hub.Deliver(RoomEvent{RoomID: "other", Public: json.RawMessage(`{}`)})
	h.hub.Deliver(RoomEvent{
		RoomID:  "room",
		Public:  json.RawMessage(`{"version":2}`),
		Private: map[string]json.RawMessage{"0": json.RawMessage(`{}`)},
	})

	state := alice.readType("state")
	if state["public"].(map[string]any)["version"] != float64(2) {
		t.Fatalf("received event of another room: %v", state)
	}
}

func TestActionIsForwardedAndAcknowledged(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")

	alice.send(map[string]any{"type": "action", "request_id": 7, "action": "roll_dice"})

	if ack := alice.readType("ack"); ack["request_id"] != float64(7) {
		t.Fatalf("unexpected ack: %v", ack)
	}
	if h.backend.actions[0] != "alice:roll_dice" {
		t.Fatalf("unexpected actions: %v", h.backend.actions)
	}
}

func TestRefusedActionKeepsTheConnection(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	h.backend.reject = &RejectedError{Status: http.StatusBadRequest, Message: "It is not your turn."}

	alice.send(map[string]any{"type": "action", "request_id": 1, "action": "roll_dice"})
	refusal := alice.readType("error")
	if refusal["message"] != "It is not your turn." || refusal["fatal"] == true {
		t.Fatalf("unexpected error: %v", refusal)
	}

	h.backend.reject = nil
	alice.send(map[string]any{"type": "action", "request_id": 2, "action": "roll_dice"})
	alice.readType("ack")
}

func TestBackendFailureHidesDetails(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	h.backend.reject = errors.New("dial tcp 10.0.0.1: refused")

	alice.send(map[string]any{"type": "action", "request_id": 1, "action": "roll_dice"})

	if message := alice.readType("error"); message["message"] != serverErrorMessage {
		t.Fatalf("leaked error: %v", message)
	}
}

func TestReplacedSessionIsDisconnected(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	h.backend.reject = &RejectedError{Status: http.StatusUnauthorized, Message: "Join again."}

	alice.send(map[string]any{"type": "action", "request_id": 1, "action": "roll_dice"})

	if message := alice.readType("error"); message["fatal"] != true {
		t.Fatalf("unexpected error: %v", message)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	for {
		if _, _, err := alice.conn.Read(ctx); err != nil {
			break
		}
	}
	if ctx.Err() != nil {
		t.Fatal("connection stayed open")
	}
}

func TestPresenceFollowsConnections(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	first := h.join(t, "bob")
	second := h.join(t, "bob") // a second tab of the same seat

	if message := alice.readType("presence"); len(message["online"].([]any)) == 0 {
		t.Fatalf("unexpected presence: %v", message)
	}

	first.conn.CloseNow()
	select {
	case key := <-h.presence.cleared:
		t.Fatalf("seat cleared while another tab is open: %s", key)
	case <-time.After(200 * time.Millisecond):
	}

	second.conn.CloseNow()
	select {
	case key := <-h.presence.cleared:
		if key != "presence:room:1" {
			t.Fatalf("cleared %s", key)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("seat was not cleared")
	}
}

func TestSlowClientIsDroppedWithoutBlockingOthers(t *testing.T) {
	h := NewHub(newFakePresence())
	cancelled := make(chan struct{})
	slow := &client{
		send:   make(chan []byte), // nobody reads this queue
		cancel: func() { close(cancelled) },
		roomID: "room",
	}
	h.rooms["room"] = map[*client]struct{}{slow: {}}

	done := make(chan struct{})
	go func() {
		h.Deliver(RoomEvent{RoomID: "room", Public: json.RawMessage(`{}`)})
		close(done)
	}()

	for _, finished := range []chan struct{}{done, cancelled} {
		select {
		case <-finished:
		case <-time.After(time.Second):
			t.Fatal("hub blocked on a slow client")
		}
	}
}

func TestDisconnectsDuringDeliveryDoNotPanic(t *testing.T) {
	h := newHarness(t)
	stop := make(chan struct{})
	var deliveries sync.WaitGroup
	deliveries.Add(1)
	go func() {
		defer deliveries.Done()
		for {
			select {
			case <-stop:
				return
			default:
				h.hub.Deliver(RoomEvent{
					RoomID:  "room",
					Public:  json.RawMessage(`{"version":2}`),
					Private: map[string]json.RawMessage{"0": json.RawMessage(`{}`)},
				})
			}
		}
	}()

	// The flood may also overflow a client's queue, so the replies don't matter here
	for range 50 {
		conn := h.dial(t)
		conn.send(map[string]any{"type": "hello", "room_id": "room", "token": "alice"})
		time.Sleep(time.Millisecond)
		conn.conn.CloseNow()
	}

	close(stop)
	deliveries.Wait()
}

func TestForeignOriginIsRefused(t *testing.T) {
	h := newHarness(t)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	_, response, err := websocket.Dial(ctx, h.url, &websocket.DialOptions{
		HTTPHeader: http.Header{"Origin": {"http://evil.test"}},
	})

	if err == nil || response == nil || response.StatusCode != http.StatusForbidden {
		t.Fatalf("expected 403, got %v %v", response, err)
	}
}

func TestHTTPBackendRoundTrip(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Key") != "key" {
			w.WriteHeader(http.StatusForbidden)
			return
		}
		if strings.HasSuffix(r.URL.Path, "/room/session") {
			w.Write([]byte(`{"seat":2,"public":{},"private":{}}`))
			return
		}
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte(`{"detail":"It is not your turn."}`))
	}))
	defer backend.Close()
	client := NewHTTPBackend(backend.URL, "key")

	session, err := client.Session(context.Background(), "room", "token")
	if err != nil || session.Seat != 2 {
		t.Fatalf("session: %v %v", session, err)
	}

	err = client.Action(context.Background(), "room", "token", "roll_dice", nil)
	var rejected *RejectedError
	if !errors.As(err, &rejected) || rejected.Message != "It is not your turn." {
		t.Fatalf("action: %v", err)
	}
}
