// Bots fills empty seats. Each bot is a goroutine with one WebSocket connection
// to the gateway, so an idle one costs almost nothing. Seats come from a Redis
// stream read by a consumer group, so any number of instances can share them.
package main

import (
	"context"
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

	consumer, release, err := consumerName(ctx, client, botsStream)
	if err != nil {
		log.Fatalf("consumer name: %v", err)
	}
	defer release()

	// Every instance runs the timer. That is safe because the backend ends a
	// turn only once its deadline has passed, so a second report changes nothing.
	backend := server.NewHTTPBackend(env("BACKEND_URL", "http://localhost:8000"), env("INTERNAL_API_KEY", "dev-internal-key"))
	go runTurnTimer(ctx, time.Second, redisDueRooms(client), backend.Timeout)

	queue := &summons{client: client, stream: botsStream, group: botsGroup, consumer: consumer}
	seats := newSeats(ctx, queue, func(ctx context.Context, seat bot.Seat) {
		bot.Play(ctx, url, seat, bot.Options{Delay: time.Duration(delayMs) * time.Millisecond})
	})
	if err := seats.run(ctx); err != nil {
		log.Fatalf("bots: %v", err)
	}
}
