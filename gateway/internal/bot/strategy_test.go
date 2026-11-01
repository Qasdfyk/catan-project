package bot

import "testing"

func number(n int) *int { return &n }

func baseView() View {
	return View{
		Public: Public{
			Status: "playing",
			Players: []Player{
				{Seat: 0, Color: "red", CardCount: 1},
				{Seat: 1, Color: "blue", CardCount: 5},
				{Seat: 2, Color: "white", CardCount: 2},
			},
			Game: &Game{
				TurnPhase:   "main_phase",
				CurrentSeat: 0,
				Bank:        map[string]int{"wood": 19, "brick": 19, "sheep": 19, "wheat": 19, "ore": 19},
				BoardTiles: []Tile{
					{Hex{0, 0, 0}, "ore", number(6)},
					{Hex{1, 0, -1}, "wheat", number(8)},
					{Hex{1, -1, 0}, "wood", number(5)},
					{Hex{-1, 0, 1}, "brick", number(2)},
				},
			},
		},
		Private: Private{
			Seat:       0,
			Resources:  map[string]int{},
			TradeRates: map[string]int{"wood": 4, "brick": 4, "sheep": 4, "wheat": 4, "ore": 4},
			Legal:      &Legal{},
		},
	}
}

func TestNothingToDoOnAnotherPlayersTurn(t *testing.T) {
	view := baseView()
	view.Public.Game.CurrentSeat = 1

	if action := Decide(view, false); action != nil {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestDiscardHappensOffTurnAndTakesLargestPiles(t *testing.T) {
	view := baseView()
	view.Public.Game.CurrentSeat = 1
	view.Public.Game.TurnPhase = "discard"
	view.Private.Resources = map[string]int{"wood": 6, "ore": 2}
	view.Private.Legal.MustDiscard = 4

	action := Decide(view, false)

	cards := action.Payload["cards"].(map[string]int)
	if action.Name != "discard" || cards["wood"] != 4 || cards["ore"] != 0 {
		t.Fatalf("unexpected discard: %v", action)
	}
}

func TestSetupPicksTheMostProductiveCorner(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "setup"
	poor := Position{Hex{-1, 0, 1}, 3}
	rich := Position{Hex{0, 0, 0}, 0} // touches ore 6, wheat 8 and wood 5
	view.Private.Legal.Settlements = []Position{poor, rich}

	action := Decide(view, false)

	if action.Name != "build_settlement" || action.Payload["direction"] != 0 {
		t.Fatalf("unexpected choice: %v", action)
	}
}

func TestSetupRoadWhenNoSettlementIsLegal(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "setup"
	view.Private.Legal.Roads = []Position{{Hex{0, 0, 0}, 0}}

	if action := Decide(view, false); action.Name != "build_road" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestBuildPriorityIsCityThenSettlement(t *testing.T) {
	view := baseView()
	spot := Position{Hex{0, 0, 0}, 0}
	view.Private.Legal.Settlements = []Position{spot}
	view.Private.Legal.Cities = []Position{spot}

	if action := Decide(view, false); action.Name != "upgrade_city" {
		t.Fatalf("unexpected action: %v", action)
	}

	view.Private.Legal.Cities = nil
	if action := Decide(view, false); action.Name != "build_settlement" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestEndsTurnWithNothingToDo(t *testing.T) {
	if action := Decide(baseView(), false); action.Name != "end_turn" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestFallbackEndsTheTurnInsteadOfRepeatingARefusedPlan(t *testing.T) {
	view := baseView()
	view.Private.Legal.Roads = []Position{{Hex{0, 0, 0}, 0}}

	if action := Decide(view, true); action.Name != "end_turn" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestBankTradeKeepsWhatTheNextBuildingNeeds(t *testing.T) {
	view := baseView()
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}

	action := Decide(view, false)

	if action.Name != "trade_with_bank" || action.Payload["give"] != "wood" {
		t.Fatalf("unexpected trade: %v", action)
	}
}

func TestBankTradeDoesNotAskForAnEmptyPile(t *testing.T) {
	view := baseView()
	view.Public.Game.Bank["ore"] = 0
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	view.Private.Resources = map[string]int{"wheat": 2, "wood": 4}

	if action := Decide(view, false); action.Name != "end_turn" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestRobberGoesToOpponentsAndAvoidsOwnTiles(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "move_robber"
	mine, theirs := Hex{0, 0, 0}, Hex{1, 0, -1}
	view.Private.Legal.RobberHexes = []Hex{mine, theirs}
	view.Public.Game.Settlements = []Building{
		{Position{mine, 3}, "red", "settlement"},
		{Position{theirs, 0}, "blue", "city"},
	}

	action := Decide(view, false)

	if action.Payload["hex"] != theirs {
		t.Fatalf("unexpected robber move: %v", action)
	}
}

func TestStealsFromThePlayerWithMostCards(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "steal"
	view.Private.Legal.StealTargets = []int{2, 1}

	if action := Decide(view, false); action.Payload["victim_seat"] != 1 {
		t.Fatalf("unexpected target: %v", action)
	}
}

func TestPlaysKnightBeforeRollingIfRobbedOwnTile(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "roll_dice"
	view.Public.Game.RobberHex = &Hex{0, 0, 0}
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	view.Private.Legal.PlayableDevCards = []string{"knight"}

	if action := Decide(view, false); action.Name != "play_knight" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestRollsWithoutReasonForAKnight(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "roll_dice"
	view.Private.Legal.PlayableDevCards = []string{"knight"}

	if action := Decide(view, false); action.Name != "roll_dice" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestAnswersAFairOfferOnlyWithSpareCards(t *testing.T) {
	view := baseView()
	view.Public.Game.CurrentSeat = 1
	view.Public.Game.TradeOffer = &Offer{
		ProposerSeat: 1,
		Give:         map[string]int{"wood": 1},
		Get:          map[string]int{"ore": 1},
	}
	view.Private.Resources = map[string]int{"ore": 2}

	if action := Decide(view, false); action.Payload["accept"] != true {
		t.Fatalf("unexpected answer: %v", action)
	}

	view.Private.Resources = map[string]int{"ore": 1}
	if action := Decide(view, false); action.Payload["accept"] != false {
		t.Fatalf("unexpected answer: %v", action)
	}
}

func TestAnswersAnOfferOnlyOnce(t *testing.T) {
	view := baseView()
	view.Public.Game.CurrentSeat = 1
	view.Public.Game.TradeOffer = &Offer{ProposerSeat: 1, DeclinedSeats: []int{0}}

	if action := Decide(view, false); action != nil {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestDoesNothingOnceTheGameIsOver(t *testing.T) {
	view := baseView()
	view.Public.Game.IsGameOver = true

	if action := Decide(view, false); action != nil {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestGeometryMatchesTheBoard(t *testing.T) {
	// Backend: Vertex(center, 0) is the same corner as Vertex(east, 4)
	first := Position{Hex{0, 0, 0}, 0}.vertex()
	second := Position{Hex{1, 0, -1}, 4}.vertex()
	if !same(first, second) {
		t.Fatalf("%v != %v", first, second)
	}

	ends := Position{Hex{0, 0, 0}, 0}.edgeEnds()
	if !touches(ends[0], ends[1]) {
		t.Fatalf("edge ends are not neighbors: %v", ends)
	}
}
