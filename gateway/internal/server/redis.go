package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	eventsChannel = "catan:events"
	presenceTTL   = 45 * time.Second
)

// RedisPresence keeps "presence:<room>:<seat>" keys, which expire on their own.
type RedisPresence struct {
	Client *redis.Client
}

func presenceKey(roomID string, seat int) string {
	return fmt.Sprintf("presence:%s:%d", roomID, seat)
}

func (p RedisPresence) Mark(ctx context.Context, roomID string, seats []int) error {
	pipe := p.Client.Pipeline()
	for _, seat := range seats {
		pipe.Set(ctx, presenceKey(roomID, seat), "1", presenceTTL)
	}
	_, err := pipe.Exec(ctx)
	return err
}

func (p RedisPresence) Clear(ctx context.Context, roomID string, seat int) error {
	return p.Client.Del(ctx, presenceKey(roomID, seat)).Err()
}

// ConsumeEvents forwards room events to the hub until the context ends. The
// client resubscribes after losing Redis, and the keepalive pings notice that.
func ConsumeEvents(ctx context.Context, client *redis.Client, hub *Hub) {
	subscription := client.Subscribe(ctx, eventsChannel)
	defer subscription.Close()

	for message := range subscription.Channel(redis.WithChannelSize(1024)) {
		var event RoomEvent
		if err := json.Unmarshal([]byte(message.Payload), &event); err != nil {
			log.Printf("event: %v", err)
			continue
		}
		hub.Deliver(event)
	}
}
