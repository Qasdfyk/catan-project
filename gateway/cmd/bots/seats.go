package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"log"
	"os"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

	"catan/gateway/internal/bot"
)

const (
	// refreshEvery keeps the entries of playing bots from looking idle
	refreshEvery = 30 * time.Second
	// abandonedAfter is how long an entry must sit idle before another consumer
	// takes it over. Well above refreshEvery, so a live consumer keeps its seats.
	abandonedAfter = 2 * time.Minute
	takeOverEvery  = 15 * time.Second
	readBlock      = 2 * time.Second
	ackTimeout     = 5 * time.Second
	// nameTTL frees the name of an instance that died without letting it go
	nameTTL = 3 * refreshEvery
)

// play keeps one bot in its seat until the seat is over or ctx is done.
type play func(ctx context.Context, seat bot.Seat)

// seats runs one bot per pending entry and acknowledges the entry once the
// bot is done with its seat.
type seats struct {
	ctx   context.Context
	queue *summons
	play  play

	mu sync.Mutex
	// running holds the bot of each entry, so none is started twice
	running map[string]context.CancelFunc
	wg      sync.WaitGroup
}

func newSeats(ctx context.Context, queue *summons, play play) *seats {
	return &seats{ctx: ctx, queue: queue, play: play, running: map[string]context.CancelFunc{}}
}

// start plays the entries not already playing and returns how many it started.
func (s *seats) start(entries []summon) int {
	started := 0
	for _, entry := range entries {
		var seat bot.Seat
		if err := json.Unmarshal([]byte(entry.Data), &seat); err != nil {
			// Also an entry trimmed from the stream: nothing can be played for it
			log.Printf("bot request %s: %v", entry.ID, err)
			s.ack(entry.ID)
			continue
		}

		s.mu.Lock()
		if _, ok := s.running[entry.ID]; ok {
			s.mu.Unlock()
			continue
		}
		ctx, cancel := context.WithCancel(s.ctx)
		s.running[entry.ID] = cancel
		s.mu.Unlock()
		started++

		s.wg.Add(1)
		go func() {
			defer s.wg.Done()
			s.play(ctx, seat)
			// Settled only when the seat is really over, not on shutdown or
			// when another consumer took the entry over
			if ctx.Err() == nil {
				s.ack(entry.ID)
			}
			s.mu.Lock()
			delete(s.running, entry.ID)
			s.mu.Unlock()
			cancel()
		}()
	}
	return started
}

func (s *seats) ack(id string) {
	ctx, cancel := context.WithTimeout(context.Background(), ackTimeout)
	defer cancel()
	// A failed ack leaves the entry pending: a later claim finds the seat gone
	if err := s.queue.ack(ctx, id); err != nil {
		log.Printf("ack %s: %v", id, err)
	}
}

func (s *seats) playing() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	ids := make([]string, 0, len(s.running))
	for id := range s.running {
		ids = append(ids, id)
	}
	return ids
}

// refresh keeps the entries of playing bots ours. A bot whose entry another
// consumer took over, after this one could not reach Redis for a while, stops,
// so each seat ends up with one bot.
func (s *seats) refresh(ctx context.Context) {
	ids := s.playing()
	kept, err := s.queue.refresh(ctx, ids)
	if err != nil {
		if ctx.Err() == nil {
			log.Printf("refresh seats: %v", err)
		}
		return
	}
	owned := map[string]bool{}
	for _, id := range kept {
		owned[id] = true
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, id := range ids {
		if cancel, ok := s.running[id]; ok && !owned[id] {
			log.Printf("seat %s was taken over", id)
			cancel()
		}
	}
}

// takeOver starts the bots of entries whose consumer stopped.
func (s *seats) takeOver(ctx context.Context, minIdle time.Duration) {
	entries, err := s.queue.claimAbandoned(ctx, minIdle)
	if err != nil && ctx.Err() == nil {
		log.Printf("claim seats: %v", err)
	}
	if started := s.start(entries); started > 0 {
		log.Printf("took over %d seats", started)
	}
}

// run resumes this consumer's seats, then plays new entries until ctx is done.
func (s *seats) run(ctx context.Context) error {
	if err := s.queue.createGroup(ctx); err != nil {
		return err
	}
	if moved, err := s.queue.migrate(ctx, legacyBotsKey); err != nil {
		return err
	} else if moved > 0 {
		log.Printf("moved %d seats from %s", moved, legacyBotsKey)
	}
	own, err := s.queue.ownPending(ctx)
	if err != nil {
		return err
	}
	log.Printf("bots ready as %s, resuming %d seats", s.queue.consumer, s.start(own))
	// Claiming at once shortens the time another consumer could also take them
	s.refresh(ctx)
	s.takeOver(ctx, abandonedAfter)

	go s.maintain(ctx, refreshEvery, takeOverEvery, abandonedAfter)
	for ctx.Err() == nil {
		entries, err := s.queue.readNew(ctx, readBlock)
		if err != nil {
			if ctx.Err() == nil {
				log.Printf("read summons: %v", err)
				time.Sleep(time.Second)
			}
			continue
		}
		s.start(entries)
	}
	return nil
}

func (s *seats) maintain(ctx context.Context, refreshInterval, takeOverInterval, minIdle time.Duration) {
	refresh := time.NewTicker(refreshInterval)
	defer refresh.Stop()
	takeOver := time.NewTicker(takeOverInterval)
	defer takeOver.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-refresh.C:
			s.refresh(ctx)
		case <-takeOver.C:
			s.takeOver(ctx, minIdle)
		}
	}
}

// consumerName is BOTS_CONSUMER or the host name. A name that stays the same
// across restarts lets an instance resume its own seats at once. If another
// running instance holds it, a random suffix is added, and that instance's
// seats are recovered from the group as abandoned ones once they sit idle.
func consumerName(ctx context.Context, client *redis.Client, stream string) (name string, release func(), err error) {
	base := os.Getenv("BOTS_CONSUMER")
	if base == "" {
		if base, err = os.Hostname(); err != nil {
			return "", nil, err
		}
	}
	name = base
	for {
		key := stream + ":consumer:" + name
		ok, err := client.SetNX(ctx, key, os.Getpid(), nameTTL).Result()
		if err != nil {
			return "", nil, err
		}
		if ok {
			stop := make(chan struct{})
			go func() {
				ticker := time.NewTicker(refreshEvery)
				defer ticker.Stop()
				for {
					select {
					case <-stop:
						return
					case <-ticker.C:
						client.Expire(context.Background(), key, nameTTL)
					}
				}
			}()
			release = func() {
				close(stop)
				client.Del(context.Background(), key)
			}
			return name, release, nil
		}
		suffix := make([]byte, 3)
		_, _ = rand.Read(suffix)
		name = base + "-" + hex.EncodeToString(suffix)
	}
}
