package bot

import (
	"math/rand/v2"
	"reflect"
	"slices"
	"testing"
)

func seeded(seed uint64) *rand.Rand { return rand.New(rand.NewPCG(seed, seed)) }

func setupView() View {
	view := baseView()
	view.Public.Game.TurnPhase = "setup"
	for direction := range 6 {
		view.Private.Legal.Settlements = append(view.Private.Legal.Settlements, Position{Hex{0, 0, 0}, direction})
	}
	view.Private.Legal.Settlements = append(view.Private.Legal.Settlements, Position{Hex{-1, 0, 1}, 3})
	return view
}

func TestMediumDoesNotDependOnChance(t *testing.T) {
	views := []View{setupView(), baseView()}
	views[1].Public.Game.TurnPhase = "move_robber"
	views[1].Private.Legal.RobberHexes = []Hex{{0, 0, 0}, {1, 0, -1}}
	views[1].Public.Game.Settlements = []Building{{Position{Hex{1, 0, -1}, 0}, "blue", "city"}}

	for _, view := range views {
		want := Decide(view, false, "medium", nil)
		for seed := range uint64(20) {
			if got := Decide(view, false, "medium", seeded(seed)); !reflect.DeepEqual(got, want) {
				t.Fatalf("seed %d: %v, want %v", seed, got, want)
			}
		}
	}
}

func TestUnknownLevelPlaysAsMedium(t *testing.T) {
	view := setupView()
	want := Decide(view, false, "medium", nil)
	for _, level := range []string{"", "expert"} {
		if got := Decide(view, false, level, seeded(3)); !reflect.DeepEqual(got, want) {
			t.Fatalf("%q: %v, want %v", level, got, want)
		}
	}
}

func TestEasyBuildsOnOneOfTheThreeBestCorners(t *testing.T) {
	view := setupView()
	values := []int{}
	for _, option := range view.Private.Legal.Settlements {
		values = append(values, vertexValue(view, option.vertex()))
	}
	slices.Sort(values)
	third := values[len(values)-3]

	chosen := map[int]bool{}
	for seed := range uint64(50) {
		action := Decide(view, false, "easy", seeded(seed))
		spot := Position{action.Payload["hex"].(Hex), action.Payload["direction"].(int)}
		if value := vertexValue(view, spot.vertex()); value < third {
			t.Fatalf("seed %d chose a corner worth %d, the third best is %d", seed, value, third)
		}
		chosen[spot.Direction] = true
	}
	if len(chosen) < 2 {
		t.Fatalf("easy always chose the same corner: %v", chosen)
	}
}

func TestEasyIsRepeatableWithTheSameSeed(t *testing.T) {
	view := setupView()
	for seed := range uint64(10) {
		first := Decide(view, false, "easy", seeded(seed))
		if second := Decide(view, false, "easy", seeded(seed)); !reflect.DeepEqual(first, second) {
			t.Fatalf("seed %d: %v then %v", seed, first, second)
		}
	}
}

func TestEasyRobberAndStealAreRandom(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "move_robber"
	mine, theirs := Hex{0, 0, 0}, Hex{1, 0, -1}
	view.Private.Legal.RobberHexes = []Hex{mine, theirs}
	view.Public.Game.Settlements = []Building{
		{Position{mine, 3}, "red", "settlement"},
		{Position{theirs, 0}, "blue", "city"},
	}
	steal := baseView()
	steal.Public.Game.TurnPhase = "steal"
	steal.Private.Legal.StealTargets = []int{2, 1}

	hexes, victims := map[Hex]bool{}, map[int]bool{}
	for seed := range uint64(40) {
		hexes[Decide(view, false, "easy", seeded(seed)).Payload["hex"].(Hex)] = true
		victims[Decide(steal, false, "easy", seeded(seed)).Payload["victim_seat"].(int)] = true
	}
	if len(hexes) != 2 || len(victims) != 2 {
		t.Fatalf("expected every option to come up: %v %v", hexes, victims)
	}
}

func TestEasyRollsInsteadOfAKnightForDefence(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "roll_dice"
	view.Public.Game.RobberHex = &Hex{0, 0, 0}
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	view.Private.Legal.PlayableDevCards = []string{"knight"}

	if action := Decide(view, false, "easy", seeded(1)); action.Name != "roll_dice" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestEasyPlaysCardsOnlySometimes(t *testing.T) {
	view := baseView()
	view.Private.Legal.PlayableDevCards = []string{"knight"}

	played := 0
	for seed := range uint64(100) {
		if Decide(view, false, "easy", seeded(seed)).Name == "play_knight" {
			played++
		}
	}
	if played == 0 || played == 100 {
		t.Fatalf("played the knight in %d of 100 turns", played)
	}
}

func TestEasyTradesWithTheBankOnlyWithAFullHand(t *testing.T) {
	view := baseView()
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	view.Private.Resources = map[string]int{"ore": 1, "wheat": 2, "wood": 4}

	if action := Decide(view, false, "easy", seeded(1)); action.Name != "end_turn" {
		t.Fatalf("unexpected action: %v", action)
	}

	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}
	if action := Decide(view, false, "easy", seeded(1)); action.Name != "trade_with_bank" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestEasyStillDiscardsAndAnswersOffers(t *testing.T) {
	view := baseView()
	view.Public.Game.CurrentSeat = 1
	view.Private.Resources = map[string]int{"wood": 6, "ore": 2}
	view.Private.Legal.MustDiscard = 4
	if action := Decide(view, false, "easy", seeded(1)); action.Name != "discard" {
		t.Fatalf("unexpected action: %v", action)
	}

	view.Private.Legal.MustDiscard = 0
	view.Public.Game.TradeOffer = &Offer{ProposerSeat: 1, Give: map[string]int{"ore": 1}, Get: map[string]int{"wood": 1}}
	if action := Decide(view, false, "easy", seeded(1)); action.Payload["accept"] != true {
		t.Fatalf("unexpected answer: %v", action)
	}
}
