package server

import (
	"context"
	"fmt"
	"maps"
	"os"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

// redisForTest connects to the Redis of the local stack, or skips the test.
func redisForTest(t *testing.T) *redis.Client {
	t.Helper()
	url := os.Getenv("REDIS_URL")
	if url == "" {
		url = "redis://localhost:6379/0"
	}
	options, err := redis.ParseURL(url)
	if err != nil {
		t.Fatal(err)
	}
	client := redis.NewClient(options)
	t.Cleanup(func() { client.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		t.Skipf("no Redis at %s: %v", url, err)
	}
	return client
}

// connectionsNamed lists the IDs and commands of the connections with this name.
func connectionsNamed(ctx context.Context, admin *redis.Client, name string) map[string]string {
	list, _ := admin.ClientList(ctx).Result()
	found := map[string]string{}
	for _, line := range strings.Split(list, "\n") {
		fields := map[string]string{}
		for _, field := range strings.Fields(line) {
			key, value, _ := strings.Cut(field, "=")
			fields[key] = value
		}
		if fields["name"] == name {
			found[fields["id"]] = fields["cmd"]
		}
	}
	return found
}

// The reader's Redis connections are killed again and again while the backend
// writes, and every event must still arrive once and in order.
func TestReaderLosesNothingWhenItsRedisConnectionDrops(t *testing.T) {
	admin := redisForTest(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	key := fmt.Sprintf("test:events:%d", time.Now().UnixNano())
	t.Cleanup(func() { admin.Del(context.Background(), key) })

	// Without retries inside go-redis, each kill reaches the reader as an error.
	options := *admin.Options()
	options.ClientName = "reader-" + key
	options.MaxRetries = -1
	readerRedis := redis.NewClient(&options)
	defer readerRedis.Close()

	metrics := &Metrics{}
	hub := NewHub(newFakePresence(), metrics)
	c := roomClient(hub, 4096)
	startReader(t, RedisEventLog{Client: readerRedis, Key: key}, hub, &fakeBackend{})
	for !slices.Contains(slices.Collect(maps.Values(connectionsNamed(ctx, admin, options.ClientName))), "xread") {
		if ctx.Err() != nil {
			t.Fatal("reader did not start")
		}
		time.Sleep(5 * time.Millisecond)
	}

	const total = 3000
	written := make(chan error, 1)
	go func() {
		for version := range total {
			data := fmt.Sprintf(`{"room_id":"room","public":{"version":%d},"private":{"0":{}}}`, version)
			err := admin.XAdd(ctx, &redis.XAddArgs{Stream: key, Values: map[string]any{"data": data}}).Err()
			if err != nil {
				written <- err
				return
			}
			if version%20 == 0 {
				time.Sleep(time.Millisecond)
			}
		}
		written <- nil
	}()

	kills := 0
	received := make([]int, 0, total)
	killer := time.NewTicker(15 * time.Millisecond)
	defer killer.Stop()
	for len(received) < total {
		select {
		case <-killer.C:
			if len(received) < total/2 || kills < 5 {
				for id := range connectionsNamed(ctx, admin, options.ClientName) {
					if admin.Do(ctx, "CLIENT", "KILL", "ID", id).Err() == nil {
						kills++
					}
				}
			}
		case <-ctx.Done():
			t.Fatalf("received %d of %d events", len(received), total)
		default:
			received = append(received, receiveVersions(t, c, 1)...)
		}
	}

	if err := <-written; err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(received, versionsFrom(0, total-1)) {
		t.Fatal("events were lost, repeated or reordered")
	}
	if kills == 0 || metrics.EventReadErrors.Load() == 0 {
		t.Fatalf("the connection never dropped: %d kills, %d errors", kills, metrics.EventReadErrors.Load())
	}
	if metrics.Resyncs.Load() != 0 {
		t.Fatalf("resynced %d times", metrics.Resyncs.Load())
	}
	t.Logf("%d events through %d killed connections and %d read errors", total, kills, metrics.EventReadErrors.Load())
}
