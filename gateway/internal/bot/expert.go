package bot

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math/rand/v2"
	"os/exec"
	"sync"
	"time"
)

// ExpertLevel is the bot that searches: the ISMCTS bot of catan-analysis-engine
// (include/catan/expert.hpp there). It runs in a separate program, catan_expert,
// which this package keeps running and talks to through its stdin and stdout.
const ExpertLevel = "expert"

// expertTimeout bounds one question to the engine: its own time limit plus
// reading the record and starting up.
const expertTimeout = 10 * time.Second

// RecordSource returns the record of a running game so far (docs/game-record.md).
type RecordSource func(ctx context.Context, roomID string) (json.RawMessage, error)

// Expert asks catan_expert for the moves of expert seats. The engine reads the
// record of the game, follows what the seat has seen of the other hands, and
// answers with a move. One process serves every expert seat; it answers
// questions concurrently and is started again if it dies.
//
// The engine only decides what the hard bot would also have to decide: the
// hard bot's answer says whether the seat has a move at all, and stands in
// when the engine fails, so an expert seat never stalls a game.
type Expert struct {
	// Command starts the engine, for instance
	// {"catan_expert", "--elites", "elites.json", "--time-ms", "1000", "--threads", "4"}.
	Command []string
	Record  RecordSource

	mu      sync.Mutex
	stdin   io.WriteCloser
	pending map[int64]chan expertReply
	next    int64
	warned  bool
}

type expertReply struct {
	ID       int64          `json:"id"`
	Action   *string        `json:"action"`
	Payload  map[string]any `json:"payload"`
	Searched bool           `json:"searched"`
	Playouts int            `json:"playouts"`
	Ms       float64        `json:"ms"`
	Error    string         `json:"error"`
}

// errEngineGone fails the questions of an engine that exited.
var errEngineGone = errors.New("catan_expert exited")

// decide is the move of an expert seat. Without an engine, or when it fails,
// the seat plays as the hard bot.
func (e *Expert) decide(ctx context.Context, roomID string, view View, fallback bool, rng *rand.Rand) *Action {
	hard := Decide(view, fallback, "hard", rng)
	if hard == nil || fallback || e == nil || len(e.Command) == 0 || e.Record == nil {
		return hard
	}
	move, err := e.Move(ctx, roomID, view.Private.Seat)
	if err != nil {
		if ctx.Err() == nil {
			log.Printf("expert in %s: %v; playing as hard", roomID, err)
		}
		return hard
	}
	if move == nil {
		// The record is newer than this view and the move is no longer the
		// seat's; the hard bot's move will be refused or overtaken the same way.
		return hard
	}
	return move
}

// Move asks the engine for the move of seat in the room. Nil without an error
// means the engine sees no move for the seat now.
func (e *Expert) Move(ctx context.Context, roomID string, seat int) (*Action, error) {
	ctx, cancel := context.WithTimeout(ctx, expertTimeout)
	defer cancel()
	record, err := e.Record(ctx, roomID)
	if err != nil {
		return nil, fmt.Errorf("record: %w", err)
	}
	request, _ := json.Marshal(map[string]any{"seat": seat, "record": record})

	id, answer, err := e.send(request)
	if err != nil {
		return nil, err
	}
	select {
	case reply := <-answer:
		if reply.Error != "" {
			return nil, errors.New(reply.Error)
		}
		if reply.Action == nil {
			return nil, nil
		}
		payload := reply.Payload
		if payload == nil {
			payload = map[string]any{}
		}
		return &Action{Name: *reply.Action, Payload: payload}, nil
	case <-ctx.Done():
		e.mu.Lock()
		delete(e.pending, id)
		e.mu.Unlock()
		return nil, ctx.Err()
	}
}

// send writes one request, starting the engine first if it is not running.
func (e *Expert) send(request []byte) (int64, chan expertReply, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.stdin == nil {
		if err := e.start(); err != nil {
			return 0, nil, err
		}
	}
	e.next++
	id := e.next
	// The id goes in front of the request's own fields
	line := append([]byte(fmt.Sprintf(`{"id":%d,`, id)), request[1:]...)
	line = append(line, '\n')
	answer := make(chan expertReply, 1)
	e.pending[id] = answer
	if _, err := e.stdin.Write(line); err != nil {
		delete(e.pending, id)
		return 0, nil, err
	}
	return id, answer, nil
}

// start runs the engine and a goroutine that hands each answer to its
// question. Called with mu held.
func (e *Expert) start() error {
	cmd := exec.Command(e.Command[0], e.Command[1:]...)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		if !e.warned {
			e.warned = true
			log.Printf("expert: cannot start %s: %v", e.Command[0], err)
		}
		return err
	}
	e.stdin = stdin
	e.pending = map[int64]chan expertReply{}
	go func() {
		scanner := bufio.NewScanner(stdout)
		scanner.Buffer(make([]byte, 64<<10), 1<<20)
		for scanner.Scan() {
			var reply expertReply
			if json.Unmarshal(scanner.Bytes(), &reply) != nil {
				continue
			}
			e.mu.Lock()
			answer := e.pending[reply.ID]
			delete(e.pending, reply.ID)
			e.mu.Unlock()
			if answer != nil {
				answer <- reply
			}
		}
		err := cmd.Wait()
		log.Printf("expert: catan_expert exited: %v", err)
		e.mu.Lock()
		if e.stdin == stdin {
			e.stdin = nil
			for id, answer := range e.pending {
				answer <- expertReply{ID: id, Error: errEngineGone.Error()}
			}
			e.pending = map[int64]chan expertReply{}
		}
		e.mu.Unlock()
	}()
	return nil
}

// Close ends the engine: it answers what it was asked and exits.
func (e *Expert) Close() {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.stdin != nil {
		e.stdin.Close()
		e.stdin = nil
	}
}
