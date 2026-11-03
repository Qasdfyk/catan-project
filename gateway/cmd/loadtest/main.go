// Loadtest measures fan-out: it opens connections, publishes room events through
// Redis and times their delivery. By default it joins the running stack with real
// player sessions; -socketio targets benchmarks/socketio_baseline.py instead.
//
//	go run ./cmd/loadtest -players 4000 -rate 1 -seconds 15
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/coder/websocket"
	"github.com/redis/go-redis/v9"
)

const roomSize = 4

type session struct {
	RoomID string `json:"room_id"`
	Token  string `json:"token"`
}

func post(url string, body string, out any) error {
	response, err := http.Post(url, "application/json", strings.NewReader(body))
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("%s: %d", url, response.StatusCode)
	}
	return json.NewDecoder(response.Body).Decode(out)
}

func main() {
	api := flag.String("api", "http://127.0.0.1:8000", "backend URL")
	ws := flag.String("ws", "ws://127.0.0.1:8080/ws", "gateway URL")
	redisURL := flag.String("redis", "redis://127.0.0.1:6379/0", "Redis URL")
	players := flag.Int("players", 400, "connections")
	rate := flag.Float64("rate", 1, "events per room per second")
	seconds := flag.Int("seconds", 15, "measurement time")
	size := flag.Int("size", 7700, "event size in bytes")
	socketio := flag.String("socketio", "", "URL of the python-socketio baseline, instead of the gateway")
	flag.Parse()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	options, err := redis.ParseURL(*redisURL)
	if err != nil {
		panic(err)
	}
	publisher := redis.NewClient(options)

	rooms := *players / roomSize
	roomIDs := make([]string, rooms)
	var failed atomic.Int64
	var measuring atomic.Bool
	var mu sync.Mutex
	var latencies []float64

	var setup sync.WaitGroup
	limiter := make(chan struct{}, 32)
	start := time.Now()
	receive := func(conn *websocket.Conn) {
		for {
			_, data, err := conn.Read(ctx)
			if err != nil {
				return
			}
			if *socketio != "" && string(data) == "2" {
				conn.Write(ctx, websocket.MessageText, []byte("3"))
				continue
			}
			if !measuring.Load() {
				continue
			}
			if at := bytes.Index(data, []byte(`"sent_at":`)); at >= 0 {
				tail := bytes.TrimLeft(data[at+10:], " ")
				end := bytes.IndexAny(tail, ",}")
				sent, _ := strconv.ParseInt(string(tail[:end]), 10, 64)
				latency := float64(time.Now().UnixNano()-sent) / 1e6
				mu.Lock()
				latencies = append(latencies, latency)
				mu.Unlock()
			}
		}
	}

	joinGateway := func(room int) {
		sessions := make([]session, roomSize)
		if err := post(*api+"/api/rooms", `{"name":"p0"}`, &sessions[0]); err != nil {
			failed.Add(roomSize)
			return
		}
		roomIDs[room] = sessions[0].RoomID
		for seat := 1; seat < roomSize; seat++ {
			url := fmt.Sprintf("%s/api/rooms/%s/join", *api, sessions[0].RoomID)
			if err := post(url, fmt.Sprintf(`{"name":"p%d"}`, seat), &sessions[seat]); err != nil {
				failed.Add(1)
			}
		}
		for _, player := range sessions {
			conn, _, err := websocket.Dial(ctx, *ws, nil)
			if err != nil {
				failed.Add(1)
				continue
			}
			conn.SetReadLimit(1 << 20)
			hello, _ := json.Marshal(map[string]string{"type": "hello", "room_id": player.RoomID, "token": player.Token})
			conn.Write(ctx, websocket.MessageText, hello)
			go receive(conn)
		}
	}

	joinSocketIO := func(room int) {
		roomIDs[room] = fmt.Sprintf("room-%d", room)
		for range roomSize {
			conn, _, err := websocket.Dial(ctx, *socketio, nil)
			if err != nil {
				failed.Add(1)
				continue
			}
			conn.SetReadLimit(1 << 20)
			conn.Read(ctx)
			conn.Write(ctx, websocket.MessageText, []byte("40"))
			conn.Read(ctx)
			conn.Write(ctx, websocket.MessageText, []byte(fmt.Sprintf(`42["join",%q]`, roomIDs[room])))
			go receive(conn)
		}
	}

	for room := range rooms {
		setup.Add(1)
		limiter <- struct{}{}
		go func() {
			defer setup.Done()
			defer func() { <-limiter }()
			if *socketio != "" {
				joinSocketIO(room)
			} else {
				joinGateway(room)
			}
		}()
	}
	setup.Wait()
	fmt.Printf("connected %d/%d in %s\n", *players-int(failed.Load()), *players, time.Since(start).Round(time.Millisecond))
	time.Sleep(2 * time.Second)

	padding := strings.Repeat("x", *size)
	interval := time.Duration(float64(time.Second) / (*rate * float64(rooms)))
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	measuring.Store(true)
	end := time.Now().Add(time.Duration(*seconds) * time.Second)
	sent := 0
	for time.Now().Before(end) {
		<-ticker.C
		event := fmt.Sprintf(
			`{"room_id":%q,"public":{"sent_at":%d,"pad":%q},"private":{"0":{},"1":{},"2":{},"3":{}}}`,
			roomIDs[sent%rooms], time.Now().UnixNano(), padding,
		)
		publisher.Publish(ctx, "catan:events", event)
		sent++
	}
	time.Sleep(3 * time.Second)
	measuring.Store(false)

	mu.Lock()
	defer mu.Unlock()
	sort.Float64s(latencies)
	count := len(latencies)
	if count == 0 {
		fmt.Println("no messages delivered")
		return
	}
	fmt.Printf("events=%d delivered=%d/%d p50=%.1fms p99=%.1fms max=%.1fms\n",
		sent, count, sent*roomSize, latencies[count/2], latencies[count*99/100], latencies[count-1])
}
