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
	chatChannel   = "catan:chat"
	presenceTTL   = 45 * time.Second

	chatHistorySize = 50
	chatHistoryTTL  = 24 * time.Hour
)

// ChatStore keeps the room's recent messages and passes new ones to all gateways.
type ChatStore interface {
	Publish(ctx context.Context, message ChatMessage) error
	Recent(ctx context.Context, roomID string) ([]ChatMessage, error)
}

// RedisChat stores history in the list "chat:<room>".
type RedisChat struct {
	Client *redis.Client
}

func chatKey(roomID string) string { return "chat:" + roomID }

func (c RedisChat) Publish(ctx context.Context, message ChatMessage) error {
	encoded, err := json.Marshal(message)
	if err != nil {
		return err
	}
	key := chatKey(message.RoomID)
	pipe := c.Client.TxPipeline()
	pipe.RPush(ctx, key, encoded)
	pipe.LTrim(ctx, key, -chatHistorySize, -1)
	pipe.Expire(ctx, key, chatHistoryTTL)
	pipe.Publish(ctx, chatChannel, encoded)
	_, err = pipe.Exec(ctx)
	return err
}

func (c RedisChat) Recent(ctx context.Context, roomID string) ([]ChatMessage, error) {
	stored, err := c.Client.LRange(ctx, chatKey(roomID), 0, -1).Result()
	if err != nil {
		return nil, err
	}
	messages := make([]ChatMessage, 0, len(stored))
	for _, entry := range stored {
		var message ChatMessage
		if err := json.Unmarshal([]byte(entry), &message); err == nil {
			messages = append(messages, message)
		}
	}
	return messages, nil
}

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

// ConsumeEvents forwards room events and chat to the hub until the context
// ends. The client resubscribes after losing Redis, and keepalive pings notice that.
func ConsumeEvents(ctx context.Context, client *redis.Client, hub *Hub) {
	subscription := client.Subscribe(ctx, eventsChannel, chatChannel)
	defer subscription.Close()

	for message := range subscription.Channel(redis.WithChannelSize(1024)) {
		if message.Channel == chatChannel {
			var chat ChatMessage
			if err := json.Unmarshal([]byte(message.Payload), &chat); err == nil {
				hub.DeliverChat(chat)
			}
			continue
		}
		var event RoomEvent
		if err := json.Unmarshal([]byte(message.Payload), &event); err != nil {
			log.Printf("event: %v", err)
			continue
		}
		hub.Deliver(event)
	}
}
