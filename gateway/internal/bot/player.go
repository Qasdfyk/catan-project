package bot

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"math/rand/v2"
	"reflect"
	"time"

	"github.com/coder/websocket"
)

const (
	reconnectDelay = 2 * time.Second
	retryDelay     = time.Second
	maxReadBytes   = 1 << 20
	// offerPatience is how long a bot waits for answers to its trade offer
	offerPatience = 5 * time.Second
)

// waitingForAnswers is a bot on its turn with an offer of its own open.
func waitingForAnswers(view View) bool {
	game := view.Public.Game
	seat := view.Private.Seat
	return game != nil && game.CurrentSeat == seat && game.TradeOffer != nil && game.TradeOffer.ProposerSeat == seat
}

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
	refused := make(chan string, 1)
	readErr := make(chan error, 1)
	go func() { readErr <- read(ctx, conn, latest, refused, options) }()

	var view View
	haveView, fallback := false, false
	request := 0
	// The last move sent and the state it was chosen on
	var sent Action
	sentVersion := -1
	var retry <-chan time.Time
	retrying := false
	// Runs while the bot waits for answers to its own offer
	var patience <-chan time.Time

	for {
		select {
		case err := <-readErr:
			return err
		case <-ctx.Done():
			return ctx.Err()
		case view = <-latest:
			haveView = true
			fallback = false
		case reason := <-refused:
			log.Printf("bot in %s: move refused: %s", seat.RoomID, reason)
			fallback = true
		case <-retry:
			retry, retrying = nil, true
		case <-patience:
			// Nobody answered in time: fallback withdraws the offer
			patience, fallback = nil, true
		}
		if !haveView {
			continue
		}
		if view.Public.Status == "finished" {
			return errSeatGone
		}

		action := Decide(view, fallback, seat.Level, options.Rand)
		if action == nil {
			if !waitingForAnswers(view) {
				patience = nil
			} else if patience == nil {
				patience = time.After(offerPatience)
			}
			continue
		}
		patience = nil

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

		// The server refused this very move on this very state. Sending it again
		// at once would only spin, so it waits for a new state, or retries in a
		// while in case the refusal was the rate limit.
		if !retrying && view.Public.Version == sentVersion && reflect.DeepEqual(*action, sent) {
			retry = time.After(retryDelay)
			continue
		}
		sent, sentVersion, retrying = *action, view.Public.Version, false

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

func read(ctx context.Context, conn *websocket.Conn, latest chan View, refused chan string, options Options) error {
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
			case refused <- message.Message:
			default:
			}
		}
	}
}
