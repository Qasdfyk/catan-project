package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"

	"catan/gateway/internal/bot"
)

// testRedis is a Redis on localhost, in a database of its own so a running
// game is not touched, with a stream name no other test uses.
func testRedis(t *testing.T) (*redis.Client, string) {
	t.Helper()
	client := redis.NewClient(&redis.Options{Addr: "localhost:6379", DB: 15})
	if err := client.Ping(context.Background()).Err(); err != nil {
		client.Close()
		t.Skipf("no Redis on localhost:6379: %v", err)
	}
	suffix := make([]byte, 4)
	_, _ = rand.Read(suffix)
	stream := "test:bots:" + hex.EncodeToString(suffix)
	t.Cleanup(func() {
		client.Del(context.Background(), stream, stream+":legacy")
		client.Close()
	})
	return client, stream
}

func queueFor(client *redis.Client, stream, consumer string) *summons {
	return &summons{client: client, stream: stream, group: botsGroup, consumer: consumer}
}

func summonSeat(t *testing.T, client *redis.Client, stream, token string) string {
	t.Helper()
	data, _ := json.Marshal(bot.Seat{RoomID: "room", Token: token, Level: "easy"})
	id, err := client.XAdd(context.Background(), &redis.XAddArgs{Stream: stream, Values: map[string]any{"data": data}}).Result()
	if err != nil {
		t.Fatal(err)
	}
	return id
}

func pendingCount(t *testing.T, client *redis.Client, stream string) int64 {
	t.Helper()
	pending, err := client.XPending(context.Background(), stream, botsGroup).Result()
	if err != nil {
		t.Fatal(err)
	}
	return pending.Count
}

func eventually(t *testing.T, what string, done func() bool) {
	t.Helper()
	for deadline := time.Now().Add(2 * time.Second); time.Now().Before(deadline); time.Sleep(5 * time.Millisecond) {
		if done() {
			return
		}
	}
	t.Fatalf("timed out waiting for %s", what)
}

// fakeBots plays a seat until the test ends it or the context is done.
type fakeBots struct {
	mu      sync.Mutex
	playing map[string]int
	plays   int
	over    map[string]chan struct{}
}

func newFakeBots() *fakeBots {
	return &fakeBots{playing: map[string]int{}, over: map[string]chan struct{}{}}
}

func (f *fakeBots) seatOver(token string) chan struct{} {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.over[token] == nil {
		f.over[token] = make(chan struct{})
	}
	return f.over[token]
}

func (f *fakeBots) play(ctx context.Context, seat bot.Seat) {
	over := f.seatOver(seat.Token)
	f.mu.Lock()
	f.playing[seat.Token]++
	f.plays++
	f.mu.Unlock()
	select {
	case <-ctx.Done():
	case <-over:
	}
	f.mu.Lock()
	f.playing[seat.Token]--
	f.mu.Unlock()
}

func (f *fakeBots) count(token string) int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.playing[token]
}

func readAndStart(t *testing.T, s *seats) int {
	t.Helper()
	entries, err := s.queue.readNew(context.Background(), 100*time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	return s.start(entries)
}

func startedSeats(t *testing.T, client *redis.Client, stream, consumer string, bots *fakeBots) (*seats, context.CancelFunc) {
	t.Helper()
	queue := queueFor(client, stream, consumer)
	if err := queue.createGroup(context.Background()); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	s := newSeats(ctx, queue, bots.play)
	t.Cleanup(func() { cancel(); s.wg.Wait() })
	return s, cancel
}

func TestSeatIsAcknowledgedOnlyWhenItIsOver(t *testing.T) {
	client, stream := testRedis(t)
	bots := newFakeBots()
	s, _ := startedSeats(t, client, stream, "a", bots)
	summonSeat(t, client, stream, "t1")

	if started := readAndStart(t, s); started != 1 {
		t.Fatalf("started %d", started)
	}
	eventually(t, "the bot", func() bool { return bots.count("t1") == 1 })
	if n := pendingCount(t, client, stream); n != 1 {
		t.Fatalf("pending while playing: %d", n)
	}

	close(bots.seatOver("t1"))
	eventually(t, "the ack", func() bool { return pendingCount(t, client, stream) == 0 })
}

func TestShutdownLeavesSeatsPendingForTheSameName(t *testing.T) {
	client, stream := testRedis(t)
	bots := newFakeBots()
	first, stop := startedSeats(t, client, stream, "a", bots)
	summonSeat(t, client, stream, "t1")
	readAndStart(t, first)
	eventually(t, "the bot", func() bool { return bots.count("t1") == 1 })

	stop()
	first.wg.Wait()
	if n := pendingCount(t, client, stream); n != 1 || bots.count("t1") != 0 {
		t.Fatalf("pending %d, playing %d", n, bots.count("t1"))
	}

	second, _ := startedSeats(t, client, stream, "a", bots)
	own, err := second.queue.ownPending(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if started := second.start(own); started != 1 {
		t.Fatalf("resumed %d", started)
	}
	eventually(t, "the resumed bot", func() bool { return bots.count("t1") == 1 })
}

func TestEntryIsNotPlayedTwiceByOneInstance(t *testing.T) {
	client, stream := testRedis(t)
	bots := newFakeBots()
	s, _ := startedSeats(t, client, stream, "a", bots)
	summonSeat(t, client, stream, "t1")
	readAndStart(t, s)

	own, _ := s.queue.ownPending(context.Background())
	claimed, _ := s.queue.claimAbandoned(context.Background(), 0)
	if started := s.start(append(own, claimed...)); started != 0 {
		t.Fatalf("started again %d", started)
	}
	eventually(t, "the bot", func() bool { return bots.count("t1") == 1 })
	bots.mu.Lock()
	defer bots.mu.Unlock()
	if bots.plays != 1 {
		t.Fatalf("plays %d", bots.plays)
	}
}

func TestOnlyIdleSeatsAreTakenOver(t *testing.T) {
	client, stream := testRedis(t)
	ctx := context.Background()
	dead, live := queueFor(client, stream, "dead"), queueFor(client, stream, "live")
	if err := dead.createGroup(ctx); err != nil {
		t.Fatal(err)
	}
	summonSeat(t, client, stream, "t1")
	summonSeat(t, client, stream, "t2")
	entries, _ := dead.readNew(ctx, 100*time.Millisecond)
	if len(entries) != 2 {
		t.Fatalf("read %d", len(entries))
	}

	time.Sleep(150 * time.Millisecond)
	// The dead consumer last refreshed t2, so only t1 looks abandoned
	if kept, err := dead.refresh(ctx, []string{entries[1].ID}); err != nil || len(kept) != 1 {
		t.Fatalf("kept %v, %v", kept, err)
	}
	claimed, err := live.claimAbandoned(ctx, 100*time.Millisecond)
	if err != nil {
		t.Fatal(err)
	}
	if len(claimed) != 1 || claimed[0].ID != entries[0].ID || claimed[0].Data != entries[0].Data {
		t.Fatalf("claimed %v", claimed)
	}
}

func TestSeatTakenOverByAnotherInstanceStopsItsBot(t *testing.T) {
	client, stream := testRedis(t)
	bots := newFakeBots()
	s, _ := startedSeats(t, client, stream, "a", bots)
	summonSeat(t, client, stream, "t1")
	readAndStart(t, s)
	eventually(t, "the bot", func() bool { return bots.count("t1") == 1 })

	// As if this instance had lost Redis for longer than abandonedAfter
	other := queueFor(client, stream, "b")
	if claimed, _ := other.claimAbandoned(context.Background(), 0); len(claimed) != 1 {
		t.Fatalf("claimed %v", claimed)
	}
	s.refresh(context.Background())

	eventually(t, "the bot to stop", func() bool { return bots.count("t1") == 0 })
	s.wg.Wait()
	owners, _ := client.XPendingExt(context.Background(), &redis.XPendingExtArgs{
		Stream: stream, Group: botsGroup, Start: "-", End: "+", Count: 10,
	}).Result()
	if len(owners) != 1 || owners[0].Consumer != "b" {
		t.Fatalf("pending %v", owners)
	}
}

func TestBrokenSummonIsAcknowledged(t *testing.T) {
	client, stream := testRedis(t)
	s, _ := startedSeats(t, client, stream, "a", newFakeBots())
	client.XAdd(context.Background(), &redis.XAddArgs{Stream: stream, Values: map[string]any{"data": "{"}})

	if started := readAndStart(t, s); started != 0 {
		t.Fatalf("started %d", started)
	}
	if n := pendingCount(t, client, stream); n != 0 {
		t.Fatalf("pending %d", n)
	}
}

func TestGroupSeesSummonsFromBeforeItExisted(t *testing.T) {
	client, stream := testRedis(t)
	ctx := context.Background()
	queue := queueFor(client, stream, "a")
	id := summonSeat(t, client, stream, "t1")

	for range 2 {
		if err := queue.createGroup(ctx); err != nil {
			t.Fatal(err)
		}
	}

	entries, err := queue.readNew(ctx, 100*time.Millisecond)
	if err != nil || len(entries) != 1 || entries[0].ID != id {
		t.Fatalf("read %v, %v", entries, err)
	}
}

func TestDeletedStreamGetsItsGroupBack(t *testing.T) {
	client, stream := testRedis(t)
	ctx := context.Background()
	queue := queueFor(client, stream, "a")
	if err := queue.createGroup(ctx); err != nil {
		t.Fatal(err)
	}
	client.Del(ctx, stream)

	if entries, err := queue.readNew(ctx, 10*time.Millisecond); err != nil || len(entries) != 0 {
		t.Fatalf("read %v, %v", entries, err)
	}
	summonSeat(t, client, stream, "t1")
	if entries, err := queue.readNew(ctx, 100*time.Millisecond); err != nil || len(entries) != 1 {
		t.Fatalf("read %v, %v", entries, err)
	}
}

func TestSeatsOfTheOldSetMoveToTheStreamOnce(t *testing.T) {
	client, stream := testRedis(t)
	ctx := context.Background()
	legacy := stream + ":legacy"
	client.SAdd(ctx, legacy, `{"room_id":"r","token":"t1"}`, `{"room_id":"r","token":"t2"}`)
	queue := queueFor(client, stream, "a")
	if err := queue.createGroup(ctx); err != nil {
		t.Fatal(err)
	}

	for _, want := range []int{2, 0} {
		if moved, err := queue.migrate(ctx, legacy); err != nil || moved != want {
			t.Fatalf("moved %d, %v; want %d", moved, err, want)
		}
	}

	entries, _ := queue.readNew(ctx, 100*time.Millisecond)
	if len(entries) != 2 || client.Exists(ctx, legacy).Val() != 0 {
		t.Fatalf("read %v", entries)
	}
}

func TestRunResumesOwnSeatsAndPlaysNewOnes(t *testing.T) {
	client, stream := testRedis(t)
	bots := newFakeBots()
	first, stop := startedSeats(t, client, stream, "a", bots)
	summonSeat(t, client, stream, "old")
	readAndStart(t, first)
	stop()
	first.wg.Wait()

	ctx, cancel := context.WithCancel(context.Background())
	s := newSeats(ctx, queueFor(client, stream, "a"), bots.play)
	finished := make(chan error)
	go func() { finished <- s.run(ctx) }()

	eventually(t, "the resumed bot", func() bool { return bots.count("old") == 1 })
	summonSeat(t, client, stream, "new")
	eventually(t, "the new bot", func() bool { return bots.count("new") == 1 })

	cancel()
	if err := <-finished; err != nil {
		t.Fatal(err)
	}
	s.wg.Wait()
	if n := pendingCount(t, client, stream); n != 2 {
		t.Fatalf("pending after shutdown %d", n)
	}
}

func TestConsumerNameIsTakenByOneInstanceAtATime(t *testing.T) {
	client, stream := testRedis(t)
	ctx := context.Background()
	t.Setenv("BOTS_CONSUMER", "host")
	t.Cleanup(func() { client.Del(ctx, stream+":consumer:host") })

	first, releaseFirst, err := consumerName(ctx, client, stream)
	if err != nil || first != "host" {
		t.Fatalf("first %q, %v", first, err)
	}
	second, releaseSecond, err := consumerName(ctx, client, stream)
	if err != nil || !strings.HasPrefix(second, "host-") {
		t.Fatalf("second %q, %v", second, err)
	}
	releaseSecond()

	releaseFirst()
	again, releaseAgain, err := consumerName(ctx, client, stream)
	if err != nil || again != "host" {
		t.Fatalf("again %q, %v", again, err)
	}
	releaseAgain()
}
