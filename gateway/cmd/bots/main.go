// Bots fills empty seats. Each bot is a goroutine with one WebSocket connection
// to the gateway, so an idle one costs almost nothing. It also runs the turn
// timer, which is why only one instance should run.
package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

	"catan/gateway/internal/bot"
	"catan/gateway/internal/server"
)

const (
	botsChannel   = "catan:bots"
	activeBotsKey = "catan:active_bots"
)

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	options, err := redis.ParseURL(env("REDIS_URL", "redis://localhost:6379/0"))
	if err != nil {
		log.Fatalf("REDIS_URL: %v", err)
	}
	client := redis.NewClient(options)
	defer client.Close()

	delayMs, err := strconv.Atoi(env("BOT_DELAY_MS", "900"))
	if err != nil {
		log.Fatalf("BOT_DELAY_MS: %v", err)
	}
	url := env("GATEWAY_URL", "ws://localhost:8080/ws")

	start := func(raw string) {
		var seat bot.Seat
		if err := json.Unmarshal([]byte(raw), &seat); err != nil {
			log.Printf("bot request: %v", err)
			return
		}
		go func() {
			bot.Play(ctx, url, seat, time.Duration(delayMs)*time.Millisecond)
			// Forgotten only when the seat is really over, not on shutdown
			if ctx.Err() == nil {
				client.SRem(context.Background(), activeBotsKey, raw)
			}
		}()
	}

	// Subscribing first means no bot is missed between the two steps. One that
	// shows up in both would only hold a second connection for the same seat.
	subscription := client.Subscribe(ctx, botsChannel)
	defer subscription.Close()
	if _, err := subscription.Receive(ctx); err != nil {
		log.Fatalf("subscribe: %v", err)
	}

	waiting, err := client.SMembers(ctx, activeBotsKey).Result()
	if err != nil {
		log.Fatalf("active bots: %v", err)
	}
	for _, raw := range waiting {
		start(raw)
	}

	backend := server.NewHTTPBackend(env("BACKEND_URL", "http://localhost:8000"), env("INTERNAL_API_KEY", "dev-internal-key"))
	go runTurnTimer(ctx, time.Second, redisDueRooms(client), backend.Timeout)

	log.Printf("bots ready, resuming %d seats", len(waiting))
	// The channel stays open after a signal, so the context has to end the loop
	messages := subscription.Channel()
	for {
		select {
		case <-ctx.Done():
			return
		case message := <-messages:
			start(message.Payload)
		}
	}
}
