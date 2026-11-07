package server

import (
	"cmp"
	"context"
	"encoding/json"
	"log"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	minRetry       = 100 * time.Millisecond
	maxRetry       = 5 * time.Second
	resyncParallel = 8
)

// EventLog is the stream the backend appends room events to.
type EventLog interface {
	Info(ctx context.Context) (StreamInfo, error)
	// Read waits a while for entries after the given ID; none is not an error.
	Read(ctx context.Context, after string) ([]LoggedEvent, error)
}

type StreamInfo struct {
	Last    string // the newest ID ever added, or "0-0"
	First   string // the oldest ID still kept
	Trimmed bool   // whether the stream has ever dropped an entry
}

type LoggedEvent struct {
	ID   string
	Data string
}

// EventReader passes room events from the stream to the hub. Every gateway
// reads the whole stream, so it is a plain reader, not a consumer group.
type EventReader struct {
	Log     EventLog
	Hub     *Hub
	Backend Backend
	Metrics *Metrics
	Retry   time.Duration // the first wait after a Redis error; doubles up to maxRetry
}

// Run reads until the context ends. It starts after the newest entry, because a
// new gateway has no clients yet, and each client starts from a snapshot.
// After an error it reads on from the last delivered ID, so a dropped
// connection loses nothing.
func (r *EventReader) Run(ctx context.Context) {
	retry := r.firstRetry()
	fail := func(err error) {
		r.Metrics.EventReadErrors.Add(1)
		log.Printf("events: %v", err)
		select {
		case <-ctx.Done():
		case <-time.After(retry):
		}
		retry = min(retry*2, maxRetry)
	}

	last := ""
	check := true
	for ctx.Err() == nil {
		if last == "" {
			info, err := r.Log.Info(ctx)
			if err != nil {
				fail(err)
				continue
			}
			last = info.Last
		}

		entries, err := r.Log.Read(ctx, last)
		if err != nil {
			fail(err)
			check = true
			continue
		}
		retry = r.firstRetry()
		if len(entries) == 0 {
			continue
		}

		// A batch shorter than the limit reached the end of the stream, and the
		// next read follows within milliseconds, far too soon for MAXLEN new
		// entries to push unread ones out. So the stream is only checked when
		// the reader is behind, or after a gap in reading: the start or an error.
		// It is checked after the read, so a trim before the read is seen.
		if check || len(entries) >= eventsReadCount {
			info, err := r.Log.Info(ctx)
			if err != nil {
				fail(err) // the batch is read again
				continue
			}
			if missedEntries(info, last) {
				// The missing events could be for any room, so every client
				// gets a new snapshot. Doing it before reading on keeps snapshots
				// newer than anything missed; the browser drops older states.
				r.Metrics.Resyncs.Add(1)
				log.Printf("events: the stream was trimmed past %s, resyncing all clients", last)
				r.Hub.Resync(ctx, r.Backend)
			}
			check = false
		}

		for _, entry := range entries {
			var event RoomEvent
			if err := json.Unmarshal([]byte(entry.Data), &event); err != nil {
				log.Printf("event %s: %v", entry.ID, err)
			} else {
				r.Hub.Deliver(event)
			}
			last = entry.ID
		}
		r.Metrics.EventsRead.Add(int64(len(entries)))
	}
}

func (r *EventReader) firstRetry() time.Duration {
	if r.Retry > 0 {
		return r.Retry
	}
	return minRetry
}

// missedEntries tells whether entries after last may have been trimmed before
// they were read. Trimming drops the oldest entries first, so a lost entry means
// the oldest one kept is newer than last. That also happens when last itself
// was trimmed just after the read, but only to a reader about MAXLEN entries
// behind, and a needless resync is harmless. (max-deleted-entry-id would be
// exact, but Redis updates it only for XDEL, not for trimming.)
func missedEntries(info StreamInfo, last string) bool {
	return info.Trimmed && compareIDs(info.First, last) > 0
}

// compareIDs orders stream IDs of the form "<milliseconds>-<sequence>".
func compareIDs(a, b string) int {
	aTime, aSeq := splitID(a)
	bTime, bSeq := splitID(b)
	if aTime != bTime {
		return cmp.Compare(aTime, bTime)
	}
	return cmp.Compare(aSeq, bSeq)
}

func splitID(id string) (uint64, uint64) {
	timePart, seqPart, _ := strings.Cut(id, "-")
	milliseconds, _ := strconv.ParseUint(timePart, 10, 64)
	sequence, _ := strconv.ParseUint(seqPart, 10, 64)
	return milliseconds, sequence
}

// Resync sends every client a new snapshot of its room, read from the backend
// the same way as when the client connected. A client whose snapshot cannot be
// read is disconnected, and the browser reconnects and starts from a snapshot.
func (h *Hub) Resync(ctx context.Context, backend Backend) {
	h.mu.RLock()
	var clients []*client
	for _, members := range h.rooms {
		for c := range members {
			clients = append(clients, c)
		}
	}
	h.mu.RUnlock()

	var workers sync.WaitGroup
	queue := make(chan *client)
	for range resyncParallel {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for c := range queue {
				session, err := backend.Session(ctx, c.roomID, c.token)
				if err != nil {
					log.Printf("resync: %v", err)
					c.cancel()
					continue
				}
				h.sendSnapshot(c, stateMessage{Type: "state", Public: session.Public, Private: session.Private})
			}
		}()
	}
	for _, c := range clients {
		queue <- c
	}
	close(queue)
	workers.Wait()
}

// sendSnapshot skips clients that left meanwhile: their queue may be closed.
func (h *Hub) sendSnapshot(c *client, message stateMessage) {
	encoded, err := json.Marshal(message)
	if err != nil {
		log.Printf("resync: %v", err)
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	if _, ok := h.rooms[c.roomID][c]; ok {
		c.enqueue(encoded)
	}
}
