package main

import (
	"context"
	"log"
	"strconv"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	deadlinesKey   = "catan:turn_deadlines"
	timerBatch     = 100
	timerWorkers   = 8
	timeoutTimeout = 5 * time.Second
)

// dueRooms lists the rooms whose turn deadline is not after now.
type dueRooms func(ctx context.Context, now time.Time) ([]string, error)

// expireTurn asks the backend to end a room's turn if its time is up.
type expireTurn func(ctx context.Context, roomID string) error

func redisDueRooms(client *redis.Client) dueRooms {
	return func(ctx context.Context, now time.Time) ([]string, error) {
		seconds := float64(now.UnixNano()) / float64(time.Second)
		return client.ZRangeByScore(ctx, deadlinesKey, &redis.ZRangeBy{
			Min:   "-inf",
			Max:   strconv.FormatFloat(seconds, 'f', -1, 64),
			Count: timerBatch,
		}).Result()
	}
}

// runTurnTimer ends overdue turns every interval until ctx is done. The
// backend removes rooms from the set itself, so anything left is retried on
// the next tick.
func runTurnTimer(ctx context.Context, interval time.Duration, due dueRooms, expire expireTurn) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-ticker.C:
			expireDue(ctx, now, due, expire)
		}
	}
}

// expireDue handles one tick. A few calls run at once so one slow room does
// not hold up the rest, and the tick waits for all of them so the same room is
// never asked twice in parallel.
func expireDue(ctx context.Context, now time.Time, due dueRooms, expire expireTurn) {
	rooms, err := due(ctx, now)
	if err != nil {
		if ctx.Err() == nil {
			log.Printf("turn deadlines: %v", err)
		}
		return
	}

	slots := make(chan struct{}, timerWorkers)
	var wg sync.WaitGroup
	for _, room := range rooms {
		slots <- struct{}{}
		wg.Add(1)
		go func() {
			defer func() { <-slots; wg.Done() }()
			callCtx, cancel := context.WithTimeout(ctx, timeoutTimeout)
			defer cancel()
			if err := expire(callCtx, room); err != nil && ctx.Err() == nil {
				log.Printf("turn timeout %s: %v", room, err)
			}
		}()
	}
	wg.Wait()
}
