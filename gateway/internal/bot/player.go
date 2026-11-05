package bot

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"math/rand/v2"
	"time"

	"github.com/coder/websocket"
)

const (
	reconnectDelay = 2 * time.Second
	maxReadBytes   = 1 << 20
)

// Seat identifies the place a bot plays in and how well it plays.
type Seat struct {
	RoomID string `json:"room_id"`
	Token  string `json:"token"`
	// Level is "easy", "medium" or "hard"; empty means DefaultLevel
	Level string `json:"level"`
}

type serverMessage struct {
	Type    string          `json:"type"`
	Public  json.RawMessage `json:"public"`
	Private json.RawMessage `json:"private"`
	Message string          `json:"message"`
	Fatal   bool            `json:"fatal"`
}

// errSeatGone ends a bot whose room finished or no longer accepts it.
var errSeatGone = errors.New("seat is gone")

// Options tune how a bot plays and let a caller watch it.
type Options struct {
	// Delay is the thinking time before each move
	Delay time.Duration
	// Rand is for the levels that leave things to chance; nil seeds one at random
	Rand *rand.Rand
	// OnState sees every state the seat receives, on the reading goroutine
	OnState func(View)
	// OnAction sees every move just before it is sent
	OnAction func(View, Action)
	// OnRefused is told when the server refuses a move
	OnRefused func(message string)
}

// Play keeps one bot in its seat until the game ends, reconnecting if needed.
func Play(ctx context.Context, url string, seat Seat, options Options) {
	if options.Rand == nil {
		options.Rand = rand.New(rand.NewPCG(rand.Uint64(), rand.Uint64()))
	}
	for ctx.Err() == nil {
		err := playConnection(ctx, url, seat, options)
		if errors.Is(err, errSeatGone) {
			return
		}
		select {
		case <-ctx.Done():
		case <-time.After(reconnectDelay):
		}
	}
}

func playConnection(ctx context.Context, url string, seat Seat, options Options) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	conn, _, err := websocket.Dial(ctx, url, nil)
	if err != nil {
		return err
	}
	defer conn.CloseNow()
	conn.SetReadLimit(maxReadBytes)

	hello, _ := json.Marshal(map[string]string{"type": "hello", "room_id": seat.RoomID, "token": seat.Token})
	if err := conn.Write(ctx, websocket.MessageText, hello); err != nil {
		return err
	}

	// The reader keeps only the newest view: thinking on an old one is pointless.
	latest := make(chan View, 1)
	refused := make(chan struct{}, 1)
	readErr := make(chan error, 1)
	go func() { readErr <- read(ctx, conn, latest, refused, options) }()

	var view View
	haveView, fallback := false, false
	request := 0

	for {
		select {
		case err := <-readErr:
			return err
		case <-ctx.Done():
			return ctx.Err()
		case view = <-latest:
			haveView = true
			fallback = false
		case <-refused:
			log.Printf("bot in %s: move refused", seat.RoomID)
			fallback = true
		}
		if !haveView {
			continue
		}
		if view.Public.Status == "finished" {
			return errSeatGone
		}

		action := Decide(view, fallback, seat.Level, options.Rand)
		if action == nil {
			continue
		}

		// Thinking time, so people can follow; a newer view replaces this one
		select {
		case <-time.After(options.Delay):
		case <-ctx.Done():
			return ctx.Err()
		}
		select {
		case view = <-latest:
			if action = Decide(view, fallback, seat.Level, options.Rand); action == nil {
				continue
			}
		default:
		}

		if options.OnAction != nil {
			options.OnAction(view, *action)
		}
		request++
		payload := action.Payload
		if payload == nil {
			payload = map[string]any{}
		}
		message, _ := json.Marshal(map[string]any{
			"type": "action", "request_id": request, "action": action.Name, "payload": payload,
		})
		if err := conn.Write(ctx, websocket.MessageText, message); err != nil {
			return err
		}
	}
}

func read(ctx context.Context, conn *websocket.Conn, latest chan View, refused chan struct{}, options Options) error {
	for {
		_, data, err := conn.Read(ctx)
		if err != nil {
			return err
		}
		var message serverMessage
		if err := json.Unmarshal(data, &message); err != nil {
			continue
		}

		switch message.Type {
		case "state":
			var view View
			if json.Unmarshal(message.Public, &view.Public) != nil || json.Unmarshal(message.Private, &view.Private) != nil {
				continue
			}
			if options.OnState != nil {
				options.OnState(view)
			}
			select {
			case <-latest:
			default:
			}
			latest <- view
		case "error":
			if message.Fatal {
				return errSeatGone
			}
			if options.OnRefused != nil {
				options.OnRefused(message.Message)
			}
			select {
			case refused <- struct{}{}:
			default:
			}
		}
	}
}
