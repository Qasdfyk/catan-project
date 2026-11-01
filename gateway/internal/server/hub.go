package server

import (
	"context"
	"encoding/json"
	"log"
	"sort"
	"sync"
	"time"
)

const presenceRefreshInterval = 20 * time.Second

// Presence stores which seats are connected, so the backend can refuse taking
// over a seat that is in use.
type Presence interface {
	Mark(ctx context.Context, roomID string, seats []int) error
	Clear(ctx context.Context, roomID string, seat int) error
}

// Hub keeps the connected clients of every room and fans out room events.
type Hub struct {
	mu       sync.RWMutex
	rooms    map[string]map[*client]struct{}
	presence Presence
	metrics  *Metrics
}

func NewHub(presence Presence, metrics *Metrics) *Hub {
	return &Hub{rooms: make(map[string]map[*client]struct{}), presence: presence, metrics: metrics}
}

// Size returns the number of open rooms and connected clients.
func (h *Hub) Size() (rooms, clients int) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for _, members := range h.rooms {
		clients += len(members)
	}
	return len(h.rooms), clients
}

func (h *Hub) add(c *client) {
	h.mu.Lock()
	clients := h.rooms[c.roomID]
	if clients == nil {
		clients = make(map[*client]struct{})
		h.rooms[c.roomID] = clients
	}
	clients[c] = struct{}{}
	online := onlineSeats(clients)
	h.mu.Unlock()

	if err := h.presence.Mark(context.Background(), c.roomID, []int{c.seat}); err != nil {
		log.Printf("presence: %v", err)
	}
	h.broadcastPresence(c.roomID, online)
}

func (h *Hub) remove(c *client) {
	h.mu.Lock()
	clients := h.rooms[c.roomID]
	delete(clients, c)
	online := onlineSeats(clients)
	if len(clients) == 0 {
		delete(h.rooms, c.roomID)
	}
	h.mu.Unlock()

	seatStillOnline := false
	for _, seat := range online {
		seatStillOnline = seatStillOnline || seat == c.seat
	}
	if !seatStillOnline {
		if err := h.presence.Clear(context.Background(), c.roomID, c.seat); err != nil {
			log.Printf("presence: %v", err)
		}
	}
	h.broadcastPresence(c.roomID, online)
}

// Deliver sends every client of the room the public state with its own
// private part. Clients that cannot keep up are dropped and resync on reconnect.
func (h *Hub) Deliver(event RoomEvent) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	clients := h.rooms[event.RoomID]
	if len(clients) == 0 {
		return
	}

	bySeat := make(map[int][]byte, 4)
	for c := range clients {
		message, ok := bySeat[c.seat]
		if !ok {
			var err error
			message, err = json.Marshal(stateMessage{
				Type:    "state",
				Public:  event.Public,
				Private: event.Private[seatKey(c.seat)],
			})
			if err != nil {
				log.Printf("event: %v", err)
				return
			}
			bySeat[c.seat] = message
		}
		c.enqueue(message)
	}
	h.metrics.EventsDelivered.Add(int64(len(clients)))
}

// DeliverChat sends a chat message to everyone in its room.
func (h *Hub) DeliverChat(message ChatMessage) {
	roomID := message.RoomID
	message.RoomID = ""
	encoded, err := json.Marshal(message)
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.rooms[roomID] {
		c.enqueue(encoded)
	}
}

// RefreshPresence extends presence keys until the context ends, so seats of a
// crashed gateway free up on their own.
func (h *Hub) RefreshPresence(ctx context.Context) {
	ticker := time.NewTicker(presenceRefreshInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for roomID, seats := range h.snapshotSeats() {
				if err := h.presence.Mark(ctx, roomID, seats); err != nil {
					log.Printf("presence: %v", err)
				}
			}
		}
	}
}

func (h *Hub) snapshotSeats() map[string][]int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	seats := make(map[string][]int, len(h.rooms))
	for roomID, clients := range h.rooms {
		seats[roomID] = onlineSeats(clients)
	}
	return seats
}

func (h *Hub) broadcastPresence(roomID string, online []int) {
	message, err := json.Marshal(presenceMessage{Type: "presence", Online: online})
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.rooms[roomID] {
		c.enqueue(message)
	}
}

func onlineSeats(clients map[*client]struct{}) []int {
	seen := make(map[int]struct{}, 4)
	online := make([]int, 0, 4)
	for c := range clients {
		if _, ok := seen[c.seat]; !ok {
			seen[c.seat] = struct{}{}
			online = append(online, c.seat)
		}
	}
	sort.Ints(online)
	return online
}
