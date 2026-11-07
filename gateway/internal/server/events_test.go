package server

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"sync"
	"testing"
	"time"
)

// fakeLog serves entries in batches of the size the Redis reader asks for.
type fakeLog struct {
	mu        sync.Mutex
	entries   []LoggedEvent
	first     string // the oldest entry kept, when the test trims the stream
	trimmed   bool
	failReads int
	reads     []string
}

func (l *fakeLog) add(roomID string, version int) {
	l.addRange(roomID, version, version)
}

// addRange adds the versions from first to last at once, as one batch can hold.
func (l *fakeLog) addRange(roomID string, first, last int) {
	l.mu.Lock()
	defer l.mu.Unlock()
	for version := first; version <= last; version++ {
		data := fmt.Sprintf(`{"room_id":%q,"public":{"version":%d},"private":{"0":{}}}`, roomID, version)
		l.entries = append(l.entries, LoggedEvent{ID: fmt.Sprintf("%d-0", version), Data: data})
	}
}

func (l *fakeLog) failNextReads(count int) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.failReads = count
}

func (l *fakeLog) Info(context.Context) (StreamInfo, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	info := StreamInfo{Last: "0-0", First: l.first, Trimmed: l.trimmed}
	if len(l.entries) > 0 {
		info.Last = l.entries[len(l.entries)-1].ID
		if info.First == "" {
			info.First = l.entries[0].ID
		}
	}
	return info, nil
}

func (l *fakeLog) Read(_ context.Context, after string) ([]LoggedEvent, error) {
	l.mu.Lock()
	l.reads = append(l.reads, after)
	if l.failReads > 0 {
		l.failReads--
		l.mu.Unlock()
		return nil, errors.New("connection reset")
	}
	var batch []LoggedEvent
	for _, entry := range l.entries {
		if compareIDs(entry.ID, after) > 0 && len(batch) < eventsReadCount {
			batch = append(batch, entry)
		}
	}
	l.mu.Unlock()
	if len(batch) == 0 {
		time.Sleep(2 * time.Millisecond)
	}
	return batch, nil
}

// roomClient is a member of "room" whose messages the test reads from its queue.
func roomClient(h *Hub, queue int) *client {
	c := &client{send: make(chan []byte, queue), cancel: func() {}, roomID: "room", hub: h}
	h.mu.Lock()
	h.rooms["room"] = map[*client]struct{}{c: {}}
	h.mu.Unlock()
	return c
}

func startReader(t *testing.T, log EventLog, hub *Hub, backend Backend) *EventReader {
	t.Helper()
	reader := &EventReader{Log: log, Hub: hub, Backend: backend, Metrics: hub.metrics, Retry: time.Millisecond}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		reader.Run(ctx)
		close(done)
	}()
	t.Cleanup(func() {
		cancel()
		<-done
	})
	return reader
}

// waitForReads returns once the reader has asked for entries, so it has
// picked the ID it starts from.
func (l *fakeLog) waitForReads(t *testing.T) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		l.mu.Lock()
		started := len(l.reads) > 0
		l.mu.Unlock()
		if started {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("reader did not start")
}

func receiveVersions(t *testing.T, c *client, count int) []int {
	t.Helper()
	versions := make([]int, 0, count)
	for len(versions) < count {
		select {
		case message := <-c.send:
			var state struct {
				Public struct {
					Version int `json:"version"`
				} `json:"public"`
			}
			if err := json.Unmarshal(message, &state); err != nil {
				t.Fatal(err)
			}
			versions = append(versions, state.Public.Version)
		case <-time.After(5 * time.Second):
			t.Fatalf("got only %v", versions)
		}
	}
	return versions
}

func versionsFrom(first, last int) []int {
	var versions []int
	for version := first; version <= last; version++ {
		versions = append(versions, version)
	}
	return versions
}

func TestReaderStartsAfterTheNewestEntry(t *testing.T) {
	hub := NewHub(newFakePresence(), &Metrics{})
	c := roomClient(hub, 16)
	log := &fakeLog{}
	log.add("room", 1)
	log.add("room", 2)

	startReader(t, log, hub, &fakeBackend{})
	log.waitForReads(t)
	log.add("room", 3)

	if got := receiveVersions(t, c, 1); got[0] != 3 {
		t.Fatalf("delivered an event from before the start: %v", got)
	}
}

func TestReaderKeepsTheOrderAcrossBatches(t *testing.T) {
	metrics := &Metrics{}
	hub := NewHub(newFakePresence(), metrics)
	c := roomClient(hub, 512)
	log := &fakeLog{}
	startReader(t, log, hub, &fakeBackend{})
	log.waitForReads(t)

	log.addRange("room", 1, 250)
	log.add("other", 251)

	if got := receiveVersions(t, c, 250); !slices.Equal(got, versionsFrom(1, 250)) {
		t.Fatalf("got %v", got)
	}
	deadline := time.Now().Add(2 * time.Second)
	for metrics.EventsRead.Load() != 251 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if metrics.EventsRead.Load() != 251 || metrics.Resyncs.Load() != 0 {
		t.Fatalf("read %d, resyncs %d", metrics.EventsRead.Load(), metrics.Resyncs.Load())
	}
}

func TestReaderResumesFromTheLastEventAfterAnError(t *testing.T) {
	metrics := &Metrics{}
	hub := NewHub(newFakePresence(), metrics)
	c := roomClient(hub, 16)
	log := &fakeLog{}
	startReader(t, log, hub, &fakeBackend{})
	log.waitForReads(t)
	log.add("room", 1)
	log.add("room", 2)
	receiveVersions(t, c, 2)

	log.failNextReads(3)
	log.addRange("room", 3, 6)

	if got := receiveVersions(t, c, 4); !slices.Equal(got, versionsFrom(3, 6)) {
		t.Fatalf("got %v", got)
	}
	if metrics.EventReadErrors.Load() != 3 {
		t.Fatalf("errors counted: %d", metrics.EventReadErrors.Load())
	}
	log.mu.Lock()
	defer log.mu.Unlock()
	for i := 1; i < len(log.reads); i++ {
		if compareIDs(log.reads[i], log.reads[i-1]) < 0 {
			t.Fatalf("read went back: %v", log.reads)
		}
	}
}

func TestReaderResyncsEveryClientWhenTheStreamWasTrimmedPastIt(t *testing.T) {
	h := newHarness(t)
	alice := h.join(t, "alice")
	bob := h.join(t, "bob")
	h.backend.mu.Lock()
	h.backend.public = json.RawMessage(`{"version":9}`)
	h.backend.mu.Unlock()
	log := &fakeLog{}
	startReader(t, log, h.hub, h.backend)
	log.waitForReads(t)

	// Entries 1 to 4 were trimmed before the reader saw them.
	log.mu.Lock()
	log.trimmed, log.first = true, "5-0"
	log.mu.Unlock()
	log.add("room", 5)

	for _, conn := range []*testConn{alice, bob} {
		if got := conn.readType("state")["public"].(map[string]any)["version"]; got != float64(9) {
			t.Fatalf("expected a snapshot first, got version %v", got)
		}
		if got := conn.readType("state")["public"].(map[string]any)["version"]; got != float64(5) {
			t.Fatalf("expected the event after the snapshot, got version %v", got)
		}
	}
	if h.metrics.Resyncs.Load() != 1 {
		t.Fatalf("resyncs: %d", h.metrics.Resyncs.Load())
	}
}

func TestReaderThatFellBehindNoticesTheTrim(t *testing.T) {
	metrics := &Metrics{}
	hub := NewHub(newFakePresence(), metrics)
	c := roomClient(hub, 512)
	backend := &fakeBackend{seats: map[string]int{"": 0}, public: json.RawMessage(`{"version":999}`)}
	log := &fakeLog{}
	log.add("room", 1)
	startReader(t, log, hub, backend)
	log.waitForReads(t)
	log.add("room", 2)
	receiveVersions(t, c, 1)

	// While the reader was away, 3 to 199 came and were trimmed.
	log.mu.Lock()
	log.trimmed, log.first = true, "200-0"
	log.mu.Unlock()
	log.addRange("room", 200, 399)

	got := receiveVersions(t, c, 201)
	if got[0] != 999 || !slices.Equal(got[1:], versionsFrom(200, 399)) {
		t.Fatalf("expected a snapshot, then 200 to 399, got %v", got)
	}
	if metrics.Resyncs.Load() != 1 {
		t.Fatalf("resyncs: %d", metrics.Resyncs.Load())
	}
}

func TestReaderThatKeptUpIgnoresTrimmingBehindIt(t *testing.T) {
	metrics := &Metrics{}
	hub := NewHub(newFakePresence(), metrics)
	c := roomClient(hub, 16)
	log := &fakeLog{trimmed: true}
	log.add("room", 1)
	startReader(t, log, hub, &fakeBackend{})
	log.waitForReads(t)
	log.add("room", 2)
	receiveVersions(t, c, 1)

	log.mu.Lock()
	log.first = "2-0" // everything before the last delivered event is gone
	log.mu.Unlock()
	log.add("room", 3)

	receiveVersions(t, c, 1)
	if metrics.Resyncs.Load() != 0 {
		t.Fatalf("resynced %d times", metrics.Resyncs.Load())
	}
}

func TestResyncDisconnectsClientsWithoutASnapshot(t *testing.T) {
	hub := NewHub(newFakePresence(), &Metrics{})
	cancelled := make(chan struct{})
	c := roomClient(hub, 1)
	c.token = "gone"
	c.cancel = func() { close(cancelled) }

	hub.Resync(context.Background(), &fakeBackend{seats: map[string]int{}})

	select {
	case <-cancelled:
	case <-time.After(time.Second):
		t.Fatal("client kept without a snapshot")
	}
}

func TestStreamIDsCompareAsNumbers(t *testing.T) {
	for _, pair := range [][2]string{{"10-0", "9-0"}, {"5-10", "5-9"}, {"1700000000000-0", "0-0"}} {
		if compareIDs(pair[0], pair[1]) != 1 || compareIDs(pair[1], pair[0]) != -1 {
			t.Fatalf("%s should come after %s", pair[0], pair[1])
		}
	}
	if compareIDs("3-1", "3-1") != 0 {
		t.Fatal("equal IDs differ")
	}
}
