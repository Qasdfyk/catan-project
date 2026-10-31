package server

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/coder/websocket"
)

const (
	maxMessageBytes = 64 << 10
	sendQueueSize   = 32
	helloTimeout    = 10 * time.Second
	writeTimeout    = 10 * time.Second
	pingInterval    = 25 * time.Second
)

const serverErrorMessage = "Something went wrong on the server. Try again."

func seatKey(seat int) string { return strconv.Itoa(seat) }

// client is one browser connection, authenticated for one seat of one room.
type client struct {
	conn   *websocket.Conn
	send   chan []byte
	cancel context.CancelFunc

	roomID string
	token  string
	seat   int
}

// enqueue never blocks the hub: a client with a full queue is disconnected.
func (c *client) enqueue(message []byte) {
	select {
	case c.send <- message:
	default:
		c.cancel()
	}
}

func (c *client) enqueueJSON(message any) {
	encoded, err := json.Marshal(message)
	if err != nil {
		log.Printf("encode: %v", err)
		return
	}
	c.enqueue(encoded)
}

// Handler serves the WebSocket endpoint.
type Handler struct {
	Hub            *Hub
	Backend        Backend
	OriginPatterns []string
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{OriginPatterns: h.OriginPatterns})
	if err != nil {
		return
	}
	defer conn.CloseNow()
	conn.SetReadLimit(maxMessageBytes)

	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()

	c := &client{conn: conn, send: make(chan []byte, sendQueueSize), cancel: cancel}

	var writers sync.WaitGroup
	writers.Add(1)
	go func() {
		defer writers.Done()
		c.writeLoop(ctx)
	}()

	if h.authenticate(ctx, c) {
		h.readLoop(ctx, c)
		h.Hub.remove(c)
	}

	// Safe only after remove: the hub is the other sender on this channel.
	// Closing lets queued errors reach the browser before the socket closes.
	close(c.send)
	writers.Wait()
	conn.Close(websocket.StatusNormalClosure, "")
}

func (h *Handler) authenticate(ctx context.Context, c *client) bool {
	helloCtx, cancel := context.WithTimeout(ctx, helloTimeout)
	defer cancel()

	var hello clientMessage
	if !readJSON(helloCtx, c.conn, &hello) || hello.Type != "hello" {
		c.enqueueJSON(errorMessage{Type: "error", Message: "Expected hello.", Fatal: true})
		return false
	}

	session, err := h.Backend.Session(helloCtx, hello.RoomID, hello.Token)
	if err != nil {
		h.reportError(c, 0, err, true)
		return false
	}
	c.roomID, c.token, c.seat = hello.RoomID, hello.Token, session.Seat

	// The first read only tells the seat; events are delivered per seat, so the
	// client must be registered before the state it starts from is read. Any
	// event overlapping this read is told apart by its version in the browser.
	h.Hub.add(c)
	session, err = h.Backend.Session(helloCtx, c.roomID, c.token)
	if err != nil {
		h.Hub.remove(c)
		h.reportError(c, 0, err, true)
		return false
	}
	c.enqueueJSON(stateMessage{Type: "state", Public: session.Public, Private: session.Private})
	return true
}

func (h *Handler) readLoop(ctx context.Context, c *client) {
	for {
		var message clientMessage
		if !readJSON(ctx, c.conn, &message) {
			return
		}
		if message.Type != "action" {
			c.enqueueJSON(errorMessage{Type: "error", RequestID: message.RequestID, Message: "Unknown message."})
			continue
		}

		// One action at a time per connection keeps a flooding client from
		// tying up more than its own share of the backend.
		err := h.Backend.Action(ctx, c.roomID, c.token, message.Action, message.Payload)
		if err == nil {
			c.enqueueJSON(ackMessage{Type: "ack", RequestID: message.RequestID})
			continue
		}
		if ctx.Err() != nil {
			return
		}
		h.reportError(c, message.RequestID, err, IsSessionFatal(err))
		if IsSessionFatal(err) {
			return
		}
	}
}

func (h *Handler) reportError(c *client, requestID int64, err error, fatal bool) {
	text := serverErrorMessage
	var rejected *RejectedError
	if errors.As(err, &rejected) {
		text = rejected.Message
	} else {
		log.Printf("backend: %v", err)
	}
	c.enqueueJSON(errorMessage{Type: "error", RequestID: requestID, Message: text, Fatal: fatal})
}

func (c *client) writeLoop(ctx context.Context) {
	ping := time.NewTicker(pingInterval)
	defer ping.Stop()
	for {
		select {
		case message, ok := <-c.send:
			if !ok {
				return
			}
			writeCtx, cancel := context.WithTimeout(context.Background(), writeTimeout)
			err := c.conn.Write(writeCtx, websocket.MessageText, message)
			cancel()
			if err != nil {
				c.cancel()
				return
			}
		case <-ping.C:
			pingCtx, cancel := context.WithTimeout(ctx, writeTimeout)
			err := c.conn.Ping(pingCtx)
			cancel()
			if err != nil {
				c.cancel()
				return
			}
		}
	}
}

func readJSON(ctx context.Context, conn *websocket.Conn, target any) bool {
	_, data, err := conn.Read(ctx)
	if err != nil {
		return false
	}
	return json.Unmarshal(data, target) == nil
}
