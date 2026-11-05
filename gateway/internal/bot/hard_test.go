package bot

import (
	"reflect"
	"testing"
)

// cityView has the hard bot with a settlement on ore 6, wheat 8 and wood 5
// and no settlements left to build, so it saves for a city.
func cityView() View {
	view := baseView()
	view.Public.Players[0].Name = "red"
	view.Public.Game.Settlements = []Building{{Position{Hex{0, 0, 0}, 0}, "red", "settlement"}}
	// The others stand far off the four tiles
	for q := range 4 {
		view.Public.Game.Settlements = append(view.Public.Game.Settlements,
			Building{Position{Hex{10 + 3*q, -5, -5 - 3*q}, 0}, "red", "settlement"})
	}
	return view
}

func TestHardSavesForTheCityInsteadOfADevCard(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 1, "sheep": 1}
	view.Private.Legal.CanBuyDevCard = true

	if action := Decide(view, false, "medium", nil); action.Name != "buy_dev_card" {
		t.Fatalf("medium: unexpected action: %v", action)
	}
	if action := Decide(view, false, "hard", nil); action.Name == "buy_dev_card" {
		t.Fatalf("hard spent the city's cards: %v", action)
	}
}

func TestHardBuysADevCardFromSpareCards(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 4, "wheat": 3, "sheep": 1}
	view.Private.Legal.CanBuyDevCard = true

	if action := Decide(view, false, "hard", nil); action.Name != "buy_dev_card" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestHardOffersPlayersOneForOneBeforeTheBank(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}
	view.Public.Game.Bank["ore"] = 10

	action := Decide(view, false, "hard", nil)

	want := &Action{"offer_trade", map[string]any{"give": map[string]int{"wood": 1}, "get": map[string]int{"ore": 1}}}
	if !reflect.DeepEqual(action, want) {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestHardStopsOfferingAfterTwoOffersInATurn(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}
	view.Public.Game.Bank["ore"] = 10
	view.Public.Game.Log = []string{"red offers a trade.", "blue's turn.", "red offers a trade.", "red offers a trade."}

	action := Decide(view, false, "hard", nil)

	if action.Name != "trade_with_bank" || action.Payload["give"] != "wood" || action.Payload["get"] != "ore" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestHardFollowsItsOwnOffer(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"wood": 4}
	offer := &Offer{ProposerSeat: 0, Give: map[string]int{"wood": 1}, Get: map[string]int{"ore": 1}}
	view.Public.Game.TradeOffer = offer

	if action := Decide(view, false, "hard", nil); action != nil {
		t.Fatalf("did not wait for answers: %v", action)
	}
	if action := Decide(view, true, "hard", nil); action.Name != "cancel_trade" {
		t.Fatalf("fallback did not withdraw the offer: %v", action)
	}

	offer.AcceptedSeats = []int{1}
	if action := Decide(view, false, "hard", nil); action != nil {
		t.Fatalf("did not wait for the last answer: %v", action)
	}

	offer.DeclinedSeats = []int{2}
	want := &Action{"confirm_trade", map[string]any{"partner_seat": 1}}
	if action := Decide(view, false, "hard", nil); !reflect.DeepEqual(action, want) {
		t.Fatalf("unexpected action: %v", action)
	}

	offer.AcceptedSeats = nil
	offer.DeclinedSeats = []int{1, 2}
	if action := Decide(view, false, "hard", nil); action.Name != "cancel_trade" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestHardAnswersByItsGoalAndTheProposersLead(t *testing.T) {
	view := cityView()
	view.Public.Game.CurrentSeat = 1
	view.Public.Game.TradeOffer = &Offer{ProposerSeat: 1, Give: map[string]int{"ore": 1}, Get: map[string]int{"wood": 1}}
	view.Private.Resources = map[string]int{"wood": 2, "ore": 1, "wheat": 2}
	for seat := range view.Public.Players {
		view.Public.Players[seat].VictoryPoints = 4
	}

	if action := Decide(view, false, "hard", nil); action.Payload["accept"] != true {
		t.Fatalf("declined a trade toward its city: %v", action)
	}

	view.Public.Players[1].VictoryPoints = 5
	if action := Decide(view, false, "hard", nil); action.Payload["accept"] != false {
		t.Fatalf("helped the leader: %v", action)
	}

	view.Public.Players[1].VictoryPoints = 4
	view.Public.Game.TradeOffer.Give = map[string]int{"sheep": 1}
	if action := Decide(view, false, "hard", nil); action.Payload["accept"] != false {
		t.Fatalf("took a card it does not need: %v", action)
	}
}

func TestHardRobsTheLeaderAndNeverItself(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "move_robber"
	mine, poor, leader := Hex{0, 0, 0}, Hex{1, 0, -1}, Hex{1, -1, 0}
	view.Private.Legal.RobberHexes = []Hex{mine, poor, leader}
	view.Public.Players[1].VictoryPoints = 3
	view.Public.Players[2].VictoryPoints = 7
	view.Public.Game.Settlements = []Building{
		{Position{mine, 3}, "red", "settlement"},
		{Position{mine, 2}, "blue", "city"},
		{Position{poor, 1}, "blue", "city"},
		{Position{leader, 5}, "white", "settlement"},
	}

	if action := Decide(view, false, "hard", nil); action.Payload["hex"] != leader {
		t.Fatalf("unexpected robber move: %v", action)
	}

	steal := baseView()
	steal.Public.Game.TurnPhase = "steal"
	steal.Public.Players[2].VictoryPoints = 7
	steal.Private.Legal.StealTargets = []int{1, 2}
	if action := Decide(steal, false, "hard", nil); action.Payload["victim_seat"] != 2 {
		t.Fatalf("unexpected victim: %v", action)
	}
}

func TestHardDiscardsWhatTheGoalDoesNotNeed(t *testing.T) {
	view := cityView()
	view.Public.Game.CurrentSeat = 1
	view.Private.Resources = map[string]int{"ore": 3, "wheat": 2, "sheep": 3}
	view.Private.Legal.MustDiscard = 4

	action := Decide(view, false, "hard", nil)

	cards := action.Payload["cards"].(map[string]int)
	if cards["sheep"] != 3 || cards["ore"]+cards["wheat"] != 1 {
		t.Fatalf("unexpected discard: %v", action)
	}
}

func TestHardPlaysAKnightToTakeTheLargestArmy(t *testing.T) {
	view := cityView()
	view.Private.Legal.PlayableDevCards = []string{"knight", "monopoly"}
	view.Public.Players[0].KnightsPlayed = 2
	view.Public.Players[1].KnightsPlayed = 3
	view.Public.Game.LargestArmyHolder = "blue"
	view.Public.Game.Bank["sheep"] = 10

	if action := Decide(view, false, "hard", nil); action.Name == "play_knight" {
		t.Fatalf("played a knight that does not take the army over a monopoly: %v", action)
	}

	view.Public.Players[0].KnightsPlayed = 3
	if action := Decide(view, false, "hard", nil); action.Name != "play_knight" {
		t.Fatalf("unexpected action: %v", action)
	}
}

func TestHardSpendsAFullHandBeforeEndingTheTurn(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "sheep": 3}
	view.Private.Legal.CanBuyDevCard = true
	// No ore in the bank and no more offers this turn: nothing brings the city closer
	view.Public.Game.Bank["ore"] = 0
	view.Public.Game.Log = []string{"red offers a trade.", "red offers a trade."}

	if action := Decide(view, false, "hard", nil); action.Name != "end_turn" {
		t.Fatalf("spent cards it is saving: %v", action)
	}

	view.Private.Resources["sheep"] = 4
	if action := Decide(view, false, "hard", nil); action.Name != "buy_dev_card" {
		t.Fatalf("kept a hand a 7 would halve: %v", action)
	}
}

func TestHardRoadHeadsForTheBestFreeCorner(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "road_building"
	home := Position{Hex{-1, 0, 1}, 3}
	view.Public.Game.Settlements = []Building{{home, "red", "settlement"}}
	// Two edges leave the far west corner; only one leads toward the rich tiles
	view.Private.Legal.Roads = []Position{{Hex{-1, 0, 1}, 2}, {Hex{-1, 0, 1}, 3}}

	action := Decide(view, false, "hard", nil)

	road := Position{action.Payload["hex"].(Hex), action.Payload["direction"].(int)}
	h := player{view, styles["hard"], nil}.plan()
	if !h.hasTarget || h.targetDist == 0 {
		t.Fatalf("no target: %+v", h.target)
	}
	if _, ok := h.roadToward([]Position{road}); !ok {
		t.Fatalf("road %v does not lead to the target", road)
	}
}

func TestHardSecondSettlementComplementsTheFirst(t *testing.T) {
	view := setupView()
	view.Public.Game.Settlements = []Building{{Position{Hex{1, 0, -1}, 5}, "red", "settlement"}}
	h := player{view, styles["hard"], nil}.plan()
	if h.production["wheat"] == 0 {
		t.Fatalf("first settlement not counted: %v", h.production)
	}
	// A tile the bot already has is worth less on the second settlement
	first := baseView()
	empty := player{first, styles["hard"], nil}.plan()
	at := cornerOf(Position{Hex{0, 0, 0}, 0}.vertex())
	if h.spotValue(at) >= empty.spotValue(at) {
		t.Fatalf("no less worth with wheat already in hand: %v >= %v", h.spotValue(at), empty.spotValue(at))
	}
}

func TestHardGoesForTheLongestRoadWhenClose(t *testing.T) {
	view := cityView()
	for direction := range 4 {
		view.Public.Game.Roads = append(view.Public.Game.Roads, Road{Position{Hex{0, 0, 0}, direction}, "red"})
	}
	view.Public.Players[1].RoadLength = 5
	view.Public.Game.LongestRoadHolder = "blue"
	view.Private.Resources = map[string]int{"wood": 1, "brick": 1}
	aside, onward := Position{Hex{1, -1, 0}, 5}, Position{Hex{0, 0, 0}, 4}
	view.Private.Legal.Roads = []Position{aside, onward}

	h := player{view, styles["hard"], nil}.plan()
	if length := h.board.longestRoad(nil); length != 4 {
		t.Fatalf("longest road %d, want 4", length)
	}
	action := Decide(view, false, "hard", nil)
	if action.Name != "build_road" || action.Payload["direction"] != 4 {
		t.Fatalf("unexpected action: %v", action)
	}

	view.Public.Players[1].RoadLength = 7
	if action := Decide(view, false, "hard", nil); action.Name != "end_turn" {
		t.Fatalf("built a road while the Longest Road is out of reach: %v", action)
	}
}

func TestHardIsRepeatable(t *testing.T) {
	views := []View{setupView(), cityView()}
	views[1].Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}
	for _, view := range views {
		want := Decide(view, false, "hard", nil)
		for seed := range uint64(10) {
			if got := Decide(view, false, "hard", seeded(seed)); !reflect.DeepEqual(got, want) {
				t.Fatalf("seed %d: %v, want %v", seed, got, want)
			}
		}
	}
}
