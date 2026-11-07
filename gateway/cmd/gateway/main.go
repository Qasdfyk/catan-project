// Gateway holds the players' WebSocket connections and the room membership.
// All game decisions stay in the Python backend.
package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"

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
	redisClient := redis.NewClient(options)
	defer redisClient.Close()

	metrics := &server.Metrics{}
	hub := server.NewHub(server.RedisPresence{Client: redisClient}, metrics)
	backend := server.NewHTTPBackend(env("BACKEND_URL", "http://localhost:8000"), env("INTERNAL_API_KEY", "dev-internal-key"))
	events := &server.EventReader{
		Log:     server.RedisEventLog{Client: redisClient, Key: server.EventsStream},
		Hub:     hub,
		Backend: backend,
		Metrics: metrics,
	}
	go events.Run(ctx)
	go server.ConsumeChat(ctx, redisClient, hub)
	go hub.RefreshPresence(ctx)

	mux := http.NewServeMux()
	mux.Handle("/ws", &server.Handler{
		Hub:            hub,
		Backend:        backend,
		Chat:           server.RedisChat{Client: redisClient},
		Metrics:        metrics,
		OriginPatterns: strings.Split(env("ALLOWED_ORIGINS", "localhost:*,127.0.0.1:*"), ","),
	})
	mux.Handle("/metrics", metrics.Handler(hub))
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok","service":"catan-gateway"}`))
	})

	httpServer := &http.Server{
		Addr:              ":" + env("PORT", "8080"),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		httpServer.Shutdown(shutdown)
	}()

	log.Printf("gateway listening on %s", httpServer.Addr)
	if err := httpServer.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
