package main

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	botsStream = "catan:bots"
	botsGroup  = "bots"
	// legacyBotsKey is the set older versions kept their seats in
	legacyBotsKey = "catan:active_bots"
	readCount     = 100
)

// summon is one stream entry: a seat for a bot, as JSON. Data is empty for an
// entry that was trimmed from the stream while it was still pending.
type summon struct {
	ID   string
	Data string
}

// summons reads the bot stream as one consumer of the group. An entry stays
// pending while its bot plays and is acknowledged when the seat is over, so a
// seat outlives the instance that played it.
type summons struct {
	client   *redis.Client
	stream   string
	group    string
	consumer string
}

func isRedisError(err error, code string) bool {
	return err != nil && strings.HasPrefix(err.Error(), code+" ")
}

// createGroup starts the group at the beginning of the stream rather than at
// its end, so seats summoned before the service first ran are played too. Old
// entries of finished games cost one connection each, ending at once.
func (s *summons) createGroup(ctx context.Context) error {
	err := s.client.XGroupCreateMkStream(ctx, s.stream, s.group, "0").Err()
	if isRedisError(err, "BUSYGROUP") {
		return nil
	}
	return err
}

// migrateScript moves the seats of the old set to the stream in one step, so
// two instances starting together cannot both copy them.
var migrateScript = redis.NewScript(`
local seats = redis.call('SMEMBERS', KEYS[1])
for _, seat in ipairs(seats) do
	redis.call('XADD', KEYS[2], '*', 'data', seat)
end
redis.call('DEL', KEYS[1])
return #seats
`)

// migrate keeps the games of a version that stored seats in a set.
func (s *summons) migrate(ctx context.Context, legacyKey string) (int, error) {
	return migrateScript.Run(ctx, s.client, []string{legacyKey, s.stream}).Int()
}

func toSummons(messages []redis.XMessage) []summon {
	entries := make([]summon, 0, len(messages))
	for _, message := range messages {
		data, _ := message.Values["data"].(string)
		entries = append(entries, summon{ID: message.ID, Data: data})
	}
	return entries
}

// readNew waits up to block for entries no consumer has seen yet.
func (s *summons) readNew(ctx context.Context, block time.Duration) ([]summon, error) {
	streams, err := s.client.XReadGroup(ctx, &redis.XReadGroupArgs{
		Group: s.group, Consumer: s.consumer, Streams: []string{s.stream, ">"}, Count: readCount, Block: block,
	}).Result()
	if errors.Is(err, redis.Nil) {
		return nil, nil
	}
	if isRedisError(err, "NOGROUP") {
		// The stream was deleted, which takes the group with it
		return nil, s.createGroup(ctx)
	}
	if err != nil {
		return nil, err
	}
	return toSummons(streams[0].Messages), nil
}

// ownPending lists the entries this consumer was given and has not
// acknowledged, which after a restart under the same name are its old seats.
func (s *summons) ownPending(ctx context.Context) ([]summon, error) {
	var entries []summon
	after := "0"
	for {
		streams, err := s.client.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group: s.group, Consumer: s.consumer, Streams: []string{s.stream, after}, Count: readCount, Block: -1,
		}).Result()
		if err != nil {
			return entries, err
		}
		messages := streams[0].Messages
		if len(messages) == 0 {
			return entries, nil
		}
		entries = append(entries, toSummons(messages)...)
		after = messages[len(messages)-1].ID
	}
}

// claimAbandoned takes over the entries nobody has touched for minIdle, which
// are those of a consumer that stopped.
func (s *summons) claimAbandoned(ctx context.Context, minIdle time.Duration) ([]summon, error) {
	var entries []summon
	start := "0-0"
	for {
		messages, next, err := s.client.XAutoClaim(ctx, &redis.XAutoClaimArgs{
			Stream: s.stream, Group: s.group, Consumer: s.consumer, MinIdle: minIdle, Start: start, Count: readCount,
		}).Result()
		if err != nil {
			return entries, err
		}
		entries = append(entries, toSummons(messages)...)
		if next == "0-0" {
			return entries, nil
		}
		start = next
	}
}

// refresh marks the given entries as recently used, so no other consumer
// takes them, and returns those still owned by this consumer. Claiming one
// that another consumer took over would take it back, so they are skipped.
func (s *summons) refresh(ctx context.Context, ids []string) ([]string, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	owned := map[string]bool{}
	start := "-"
	for {
		pending, err := s.client.XPendingExt(ctx, &redis.XPendingExtArgs{
			Stream: s.stream, Group: s.group, Consumer: s.consumer, Start: start, End: "+", Count: readCount,
		}).Result()
		if err != nil {
			return nil, err
		}
		for _, entry := range pending {
			owned[entry.ID] = true
		}
		if len(pending) < readCount {
			break
		}
		start = "(" + pending[len(pending)-1].ID
	}

	var kept []string
	for _, id := range ids {
		if owned[id] {
			kept = append(kept, id)
		}
	}
	if len(kept) == 0 {
		return nil, nil
	}
	return kept, s.client.XClaimJustID(ctx, &redis.XClaimArgs{
		Stream: s.stream, Group: s.group, Consumer: s.consumer, Messages: kept,
	}).Err()
}

func (s *summons) ack(ctx context.Context, id string) error {
	return s.client.XAck(ctx, s.stream, s.group, id).Err()
}
