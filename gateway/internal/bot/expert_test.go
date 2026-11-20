package bot

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"reflect"
	"sync"
	"testing"
)

// The test binary stands in for catan_expert: run with BOT_FAKE_ENGINE set, it
// answers every request with a road on the edge numbered by the seat, or, in
// "crash" mode, exits on the first one.
func TestMain(m *testing.M) {
	if mode := os.Getenv("BOT_FAKE_ENGINE"); mode != "" {
		fakeEngine(mode)
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func fakeEngine(mode string) {
	in := bufio.NewScanner(os.Stdin)
	in.Buffer(make([]byte, 64<<10), 1<<20)
	for in.Scan() {
		if mode == "crash" {
			os.Exit(3)
		}
		var request struct {
			ID     int64           `json:"id"`
			Seat   int             `json:"seat"`
			Record json.RawMessage `json:"record"`
		}
		json.Unmarshal(in.Bytes(), &request)
		if request.Seat == 3 {
			fmt.Printf(`{"id":%d,"action":null}`+"\n", request.ID)
			continue
		}
		fmt.Printf(`{"id":%d,"action":"build_road","payload":{"hex":{"q":0,"r":0,"s":0},"direction":%d},"searched":true}`+"\n",
			request.ID, request.Seat)
	}
}

func fakeExpert(t *testing.T, mode string) *Expert {
	t.Setenv("BOT_FAKE_ENGINE", mode)
	expert := &Expert{
		Command: []string{os.Args[0]},
		Record: func(ctx context.Context, roomID string) (json.RawMessage, error) {
			return json.RawMessage(`{"events": []}`), nil
		},
	}
	t.Cleanup(expert.Close)
	return expert
}

func TestExpertMatchesEachAnswerToItsQuestion(t *testing.T) {
	expert := fakeExpert(t, "answer")
	var wg sync.WaitGroup
	errs := make(chan error, 30)
	for i := range 30 {
		seat := i % 3
		wg.Go(func() {
			move, err := expert.Move(context.Background(), "room", seat)
			if err != nil {
				errs <- err
				return
			}
			if move.Name != "build_road" || move.Payload["direction"] != float64(seat) {
				errs <- fmt.Errorf("seat %d got %v", seat, move)
			}
		})
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Fatal(err)
	}
}

func TestExpertWithNoMoveReturnsNil(t *testing.T) {
	move, err := fakeExpert(t, "answer").Move(context.Background(), "room", 3)
	if err != nil || move != nil {
		t.Fatalf("got %v, %v", move, err)
	}
}

func TestExpertThatDiesFailsTheQuestionAndStartsAgain(t *testing.T) {
	expert := fakeExpert(t, "crash")
	if _, err := expert.Move(context.Background(), "room", 0); err == nil {
		t.Fatal("a crashed engine answered")
	}
	t.Setenv("BOT_FAKE_ENGINE", "answer")
	// The next question starts a new engine
	var move *Action
	var err error
	for range 3 {
		if move, err = expert.Move(context.Background(), "room", 1); err == nil {
			break
		}
	}
	if err != nil || move == nil || move.Payload["direction"] != float64(1) {
		t.Fatalf("after a restart: %v, %v", move, err)
	}
}

func TestExpertPlaysAsHardWithoutAnEngine(t *testing.T) {
	for _, view := range []View{setupView(), cityView()} {
		want := Decide(view, false, "hard", seeded(1))
		if got := Decide(view, false, ExpertLevel, seeded(1)); !reflect.DeepEqual(got, want) {
			t.Fatalf("Decide: %v, want %v", got, want)
		}
		var none *Expert
		if got := none.decide(context.Background(), "room", view, false, seeded(1)); !reflect.DeepEqual(got, want) {
			t.Fatalf("no engine: %v, want %v", got, want)
		}
		broken := &Expert{Command: []string{"/nonexistent/catan_expert"}, Record: func(context.Context, string) (json.RawMessage, error) {
			return nil, errors.New("no record")
		}}
		if got := broken.decide(context.Background(), "room", view, false, seeded(1)); !reflect.DeepEqual(got, want) {
			t.Fatalf("failing engine: %v, want %v", got, want)
		}
	}
}

func TestExpertAsksTheEngineOnlyWhenTheSeatHasAMove(t *testing.T) {
	asked := 0
	expert := fakeExpert(t, "answer")
	expert.Record = func(context.Context, string) (json.RawMessage, error) {
		asked++
		return json.RawMessage(`{}`), nil
	}
	view := cityView()
	view.Public.Game.CurrentSeat = view.Private.Seat + 1 // someone else's turn
	if Decide(view, false, "hard", nil) != nil {
		t.Skip("the hard bot has a move in this view")
	}
	if got := expert.decide(context.Background(), "room", view, false, nil); got != nil || asked != 0 {
		t.Fatalf("got %v after %d questions", got, asked)
	}

	view = cityView()
	got := expert.decide(context.Background(), "room", view, false, nil)
	if asked != 1 || got == nil || got.Name != "build_road" {
		t.Fatalf("got %v after %d questions", got, asked)
	}
	// A refused move falls back to the hard bot's safe move, without the engine
	if got := expert.decide(context.Background(), "room", view, true, nil); asked != 1 || reflect.DeepEqual(got, &Action{Name: "build_road"}) {
		t.Fatalf("fallback asked the engine: %v", got)
	}
}
