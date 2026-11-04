package main

import (
	"context"
	"errors"
	"slices"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestExpireDueAsksForEveryDueRoom(t *testing.T) {
	now := time.Unix(1000, 0)
	var asked time.Time
	due := func(_ context.Context, at time.Time) ([]string, error) {
		asked = at
		return []string{"a", "b", "c"}, nil
	}
	var mu sync.Mutex
	var expired []string
	expire := func(_ context.Context, room string) error {
		mu.Lock()
		defer mu.Unlock()
		expired = append(expired, room)
		if room == "b" {
			return errors.New("backend down")
		}
		return nil
	}

	expireDue(context.Background(), now, due, expire)

	slices.Sort(expired)
	if !asked.Equal(now) || !slices.Equal(expired, []string{"a", "b", "c"}) {
		t.Fatalf("asked at %v, expired %v", asked, expired)
	}
}

func TestExpireDueDoesNotWaitForASlowRoomOneByOne(t *testing.T) {
	due := func(context.Context, time.Time) ([]string, error) {
		return []string{"slow", "fast"}, nil
	}
	// The slow room only finishes once the fast one has run, so handling them
	// one by one would leave it waiting for its whole timeout
	var released atomic.Bool
	release := make(chan struct{})
	expire := func(ctx context.Context, room string) error {
		if room == "fast" {
			close(release)
			return nil
		}
		select {
		case <-release:
			released.Store(true)
		case <-ctx.Done():
		}
		return nil
	}

	expireDue(context.Background(), time.Now(), due, expire)

	if !released.Load() {
		t.Fatal("slow room held up the fast one")
	}
}

func TestExpireDueSkipsTheTickWhenListingFails(t *testing.T) {
	due := func(context.Context, time.Time) ([]string, error) {
		return nil, errors.New("redis down")
	}
	expire := func(context.Context, string) error {
		t.Error("expire called without rooms")
		return nil
	}

	expireDue(context.Background(), time.Now(), due, expire)
}

func TestRunTurnTimerKeepsTickingUntilCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	var ticks atomic.Int32
	due := func(context.Context, time.Time) ([]string, error) {
		if ticks.Add(1) == 3 {
			cancel()
		}
		return nil, errors.New("redis down")
	}
	done := make(chan struct{})
	go func() {
		runTurnTimer(ctx, time.Millisecond, due, func(context.Context, string) error { return nil })
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("timer did not stop")
	}
	if ticks.Load() < 3 {
		t.Fatalf("only %d ticks", ticks.Load())
	}
}
