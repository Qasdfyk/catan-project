// Tournament plays bots against each other over the running stack, without the
// bots service: it opens rooms through the REST API, runs every seat in this
// process and reports how often each level wins.
//
//	go run ./cmd/tournament -games 400 -levels easy,medium,medium,medium
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"math/rand/v2"
	"net/http"
	"os"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/coder/websocket"

	"catan/gateway/internal/bot"
)

const errTimeout = "timed out"

type config struct {
	api, ws string
	levels  []string
	timeout time.Duration
	delay   time.Duration
	seed    uint64
	record  *recorder
}

type session struct {
	RoomID string `json:"room_id"`
	Token  string `json:"token"`
}

func post(ctx context.Context, url string, body any, out any) error {
	data, _ := json.Marshal(body)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, url, strings.NewReader(string(data)))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("%s: %d", url, response.StatusCode)
	}
	return json.NewDecoder(response.Body).Decode(out)
}

// openRoom creates a room and fills every seat through the REST API.
func openRoom(ctx context.Context, api string, levels []string) ([]session, error) {
	seats := make([]session, len(levels))
	for seat, level := range levels {
		url := api + "/api/rooms"
		if seat > 0 {
			url = fmt.Sprintf("%s/api/rooms/%s/join", api, seats[0].RoomID)
		}
		name := map[string]string{"name": fmt.Sprintf("%s %d", level, seat)}
		if err := post(ctx, url, name, &seats[seat]); err != nil {
			return nil, err
		}
	}
	return seats, nil
}

// startGame connects as the host just long enough to start the game.
func startGame(ctx context.Context, url string, host session) error {
	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		return err
	}
	defer conn.CloseNow()
	conn.SetReadLimit(1 << 20)

	messages := []map[string]any{
		{"type": "hello", "room_id": host.RoomID, "token": host.Token},
		{"type": "action", "request_id": 1, "action": "start_game", "payload": map[string]any{}},
	}
	for _, message := range messages {
		data, _ := json.Marshal(message)
		if err := conn.Write(ctx, websocket.MessageText, data); err != nil {
			return err
		}
	}
	for {
		_, data, err := conn.Read(ctx)
		if err != nil {
			return err
		}
		var reply struct {
			Type    string `json:"type"`
			Message string `json:"message"`
		}
		json.Unmarshal(data, &reply)
		switch reply.Type {
		case "ack":
			conn.Close(websocket.StatusNormalClosure, "")
			return nil
		case "error":
			return errors.New(reply.Message)
		}
	}
}

// watch follows the game through the host's states. It is shared by the
// reading goroutine of one bot and the game that waits for the result.
type watch struct {
	mu      sync.Mutex
	turns   int
	seat    int
	winner  int
	points  []int
	refused int
}

func (w *watch) state(view bot.View) {
	w.mu.Lock()
	defer w.mu.Unlock()
	game := view.Public.Game
	if game == nil {
		return
	}
	// A turn starts whenever the current seat changes after the setup
	if game.TurnPhase != "setup" && game.CurrentSeat != w.seat {
		w.turns++
		w.seat = game.CurrentSeat
	}
	if view.Public.Status == "finished" && game.WinnerSeat != nil {
		w.winner = *game.WinnerSeat
		w.points = w.points[:0]
		for _, player := range view.Public.Players {
			w.points = append(w.points, player.VictoryPoints)
		}
	}
}

func (w *watch) refuse(string) {
	w.mu.Lock()
	w.refused++
	w.mu.Unlock()
}

func playGame(ctx context.Context, cfg config, game int) result {
	levels := seatLevels(cfg.levels, game)
	r := result{Game: game, Levels: levels, Winner: -1}
	started := time.Now()
	ctx, cancel := context.WithTimeout(ctx, cfg.timeout)
	defer cancel()

	seats, err := openRoom(ctx, cfg.api, levels)
	if err == nil {
		r.RoomID = seats[0].RoomID
		err = startGame(ctx, cfg.ws, seats[0])
	}
	if err != nil {
		r.Error = err.Error()
		return r
	}

	w := &watch{seat: -1, winner: -1}
	var wg sync.WaitGroup
	for seat, s := range seats {
		options := bot.Options{
			Delay:     cfg.delay,
			Rand:      rand.New(rand.NewPCG(cfg.seed, uint64(game*len(seats)+seat))),
			OnRefused: w.refuse,
		}
		if seat == 0 {
			options.OnState = w.state
		}
		if cfg.record != nil {
			options.OnAction = func(view bot.View, action bot.Action) {
				cfg.record.write(decision{game, s.RoomID, seat, levels[seat], view, action})
			}
		}
		wg.Go(func() {
			bot.Play(ctx, cfg.ws, bot.Seat{RoomID: s.RoomID, Token: s.Token, Level: levels[seat]}, options)
		})
	}
	wg.Wait()

	w.mu.Lock()
	defer w.mu.Unlock()
	r.Duration = time.Since(started)
	r.Turns, r.Refused, r.Winner, r.Points = w.turns, w.refused, w.winner, w.points
	if r.Winner < 0 {
		r.Error = errTimeout
		if ctx.Err() == nil {
			r.Error = "ended without a winner"
		}
	}
	cfg.record.write(struct {
		Game   int    `json:"game"`
		Result result `json:"result"`
	}{game, r})
	return r
}

type decision struct {
	Game   int        `json:"game"`
	RoomID string     `json:"room_id"`
	Seat   int        `json:"seat"`
	Level  string     `json:"level"`
	View   bot.View   `json:"view"`
	Action bot.Action `json:"action"`
}

// recorder appends one JSON line per decision and per game. A nil recorder
// writes nothing.
type recorder struct {
	mu  sync.Mutex
	out *bufio.Writer
}

func (r *recorder) write(line any) {
	if r == nil {
		return
	}
	data, err := json.Marshal(line)
	if err != nil {
		log.Printf("record: %v", err)
		return
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.out.Write(append(data, '\n'))
}

func main() {
	api := flag.String("api", "http://127.0.0.1:8000", "backend URL")
	ws := flag.String("ws", "ws://127.0.0.1:8080/ws", "gateway URL")
	games := flag.Int("games", 20, "games to play")
	levelList := flag.String("levels", "medium,medium,medium,medium", "level of each seat, rotated between games")
	parallel := flag.Int("parallel", 32, "games played at once")
	timeout := flag.Duration("timeout", 5*time.Minute, "time limit of one game, after which it counts as no result")
	// The gateway takes 10 messages a second per connection. Without a pause a
	// bot outruns it, and a refused build makes the bot end its turn.
	delay := flag.Duration("delay", 100*time.Millisecond, "thinking time of the bots before each move")
	seed := flag.Uint64("seed", 1, "seed of the bots that play by chance")
	asJSON := flag.Bool("json", false, "print the summary as JSON")
	recordPath := flag.String("record", "", "append every decision and result to this JSON lines file")
	flag.Parse()

	levels := strings.Split(*levelList, ",")
	if len(levels) < 2 || len(levels) > 4 {
		log.Fatalf("-levels needs 2 to 4 seats, got %d", len(levels))
	}
	for _, level := range levels {
		if !slices.Contains([]string{"easy", "medium", "hard"}, level) {
			log.Fatalf("unknown level %q", level)
		}
	}
	cfg := config{api: *api, ws: *ws, levels: levels, timeout: *timeout, delay: *delay, seed: *seed}

	if *recordPath != "" {
		file, err := os.OpenFile(*recordPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
		if err != nil {
			log.Fatalf("record: %v", err)
		}
		defer file.Close()
		cfg.record = &recorder{out: bufio.NewWriterSize(file, 1<<20)}
		defer cfg.record.out.Flush()
	}

	ctx := context.Background()
	results := make([]result, *games)
	slots := make(chan struct{}, *parallel)
	var wg sync.WaitGroup
	started := time.Now()
	for game := range *games {
		slots <- struct{}{}
		wg.Go(func() {
			defer func() { <-slots }()
			results[game] = playGame(ctx, cfg, game)
			r := results[game]
			log.Printf("game %d: winner %d (%v), %d turns, %s %s", game, r.Winner, r.Levels, r.Turns, r.Duration.Round(time.Millisecond), r.Error)
		})
	}
	wg.Wait()

	s := summarize(levels, results, time.Since(started))
	if *asJSON {
		out := json.NewEncoder(os.Stdout)
		out.SetIndent("", "  ")
		out.Encode(s)
		return
	}
	s.print(os.Stdout)
}
