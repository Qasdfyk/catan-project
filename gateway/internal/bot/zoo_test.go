package bot

import (
	"math"
	"reflect"
	"testing"
)

// offerView has seat 1 offering the bot ore for wood while the bot saves
// for a city, everyone on 4 points.
func offerView() View {
	view := cityView()
	view.Public.Game.CurrentSeat = 1
	view.Public.Game.TradeOffer = &Offer{ProposerSeat: 1, Give: map[string]int{"ore": 1}, Get: map[string]int{"wood": 1}}
	view.Private.Resources = map[string]int{"wood": 2, "ore": 1, "wheat": 2}
	for seat := range view.Public.Players {
		view.Public.Players[seat].VictoryPoints = 4
	}
	return view
}

func accepts(t *testing.T, view View, level string) bool {
	t.Helper()
	action := Decide(view, false, level, nil)
	if action == nil || action.Name != "respond_trade" {
		t.Fatalf("%s: unexpected action: %v", level, action)
	}
	return action.Payload["accept"] == true
}

func TestZooBalancedFairPlaysAsHard(t *testing.T) {
	trading := cityView()
	trading.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4}
	views := []View{setupView(), cityView(), trading, offerView()}
	for i, view := range views {
		want := Decide(view, false, "hard", nil)
		if got := Decide(view, false, "zoo:balanced:fair", nil); !reflect.DeepEqual(got, want) {
			t.Fatalf("view %d: %v, want %v", i, got, want)
		}
	}
}

func TestParseZoo(t *testing.T) {
	z, ok := ParseZoo("zoo:ore-wheat:wary:42")
	if !ok || z.Archetype != "ore-wheat" || z.Personality != "wary" || z.Seed != 42 || z.Trading != personalities["wary"] {
		t.Fatalf("unexpected bot: %+v %v", z, ok)
	}
	if z, ok := ParseZoo("zoo:port:loner"); !ok || z.Seed != 0 || !reflect.DeepEqual(z.Weights, archetypes["port"]) {
		t.Fatalf("no seed should mean no jitter: %+v", z)
	}
	for _, level := range []string{"hard", "zoo", "zoo:port", "zoo:pirate:fair", "zoo:port:grumpy", "zoo:port:fair:x", "zoo:port:fair:1:2"} {
		if _, ok := ParseZoo(level); ok {
			t.Fatalf("%q read as a zoo level", level)
		}
	}
	if level := ZooLevel("wood-brick", "friendly", 7); level != "zoo:wood-brick:friendly:7" {
		t.Fatalf("unexpected level %q", level)
	}
	// An unknown zoo bot plays as medium, like any unknown level
	view := setupView()
	if got, want := Decide(view, false, "zoo:pirate:fair", nil), Decide(view, false, "medium", nil); !reflect.DeepEqual(got, want) {
		t.Fatalf("%v, want %v", got, want)
	}
}

func TestJitterIsRepeatableAndStaysNearTheArchetype(t *testing.T) {
	base := archetypes["ore-wheat"]
	first, again, other := jitter(base, 5), jitter(base, 5), jitter(base, 6)
	if !reflect.DeepEqual(first, again) {
		t.Fatalf("same seed, different bots: %+v %+v", first, again)
	}
	if reflect.DeepEqual(first, other) {
		t.Fatal("different seeds gave the same bot")
	}
	if first.RoadReach != base.RoadReach {
		t.Fatalf("road reach is not a weight: %d", first.RoadReach)
	}
	// Five standard deviations either way: a draw beyond that is a bug
	limit := math.Exp(5 * jitterSpread)
	check := func(name string, got, want float64) {
		if got == want || got > want*limit || got < want/limit {
			t.Fatalf("%s: %v from %v", name, got, want)
		}
	}
	for _, resource := range resources {
		check(resource, first.Resource[resource], base.Resource[resource])
	}
	check("city", first.City, base.City)
	check("dev card", first.DevCard, base.DevCard)
	// The archetype itself is left alone
	if base.Resource["ore"] != 1.4 {
		t.Fatalf("jitter changed the archetype: %v", base.Resource)
	}
}

func TestArchetypesSettleOnTheirOwnResources(t *testing.T) {
	view := baseView()
	view.Public.Game.TurnPhase = "setup"
	// The same number on ore and on wood, far apart
	view.Public.Game.BoardTiles = []Tile{{Hex{0, 0, 0}, "ore", number(6)}, {Hex{3, -3, 0}, "wood", number(6)}}
	ore, wood := Position{Hex{0, 0, 0}, 0}, Position{Hex{3, -3, 0}, 0}
	view.Private.Legal.Settlements = []Position{wood, ore}

	for level, want := range map[string]Position{"zoo:ore-wheat:fair": ore, "zoo:wood-brick:fair": wood} {
		action := Decide(view, false, level, nil)
		if got := (Position{action.Payload["hex"].(Hex), action.Payload["direction"].(int)}); got != want {
			t.Fatalf("%s settled on %v, want %v", level, got, want)
		}
	}
}

func TestWoodBrickChasesTheLongestRoadFromFurtherBehind(t *testing.T) {
	view := cityView()
	for direction := range 4 {
		view.Public.Game.Roads = append(view.Public.Game.Roads, Road{Position{Hex{0, 0, 0}, direction}, "red"})
	}
	// Four roads against six: out of reach for hard, within it for wood-brick
	view.Public.Players[1].RoadLength = 6
	view.Public.Game.LongestRoadHolder = "blue"
	view.Private.Resources = map[string]int{"wood": 1, "brick": 1}
	view.Private.Legal.Roads = []Position{{Hex{1, -1, 0}, 5}, {Hex{0, 0, 0}, 4}}

	if action := Decide(view, false, "hard", nil); action.Name != "end_turn" {
		t.Fatalf("hard built a road: %v", action)
	}
	if action := Decide(view, false, "zoo:wood-brick:fair", nil); action.Name != "build_road" {
		t.Fatalf("wood-brick did not build a road: %v", action)
	}
}

func TestPersonalitiesAnswerOffers(t *testing.T) {
	view := offerView()
	if !accepts(t, view, "hard") || !accepts(t, view, "zoo:balanced:friendly") || accepts(t, view, "zoo:balanced:loner") {
		t.Fatal("only the loner turns down a trade toward its city")
	}

	// The proposer leads: hard and wary refuse, friendly helps anyway
	view.Public.Players[1].VictoryPoints = 5
	if accepts(t, view, "hard") || accepts(t, view, "zoo:balanced:wary") || !accepts(t, view, "zoo:balanced:friendly") {
		t.Fatal("wrong answers to the leader")
	}

	// Ahead of the bot but behind the leader: only wary refuses
	view.Public.Players[2].VictoryPoints = 6
	if !accepts(t, view, "hard") || accepts(t, view, "zoo:balanced:wary") {
		t.Fatal("wrong answers to a player ahead of the bot")
	}

	// A card the city does not need for one it does not need either
	view = offerView()
	view.Public.Game.TradeOffer.Give = map[string]int{"sheep": 1}
	if accepts(t, view, "hard") || !accepts(t, view, "zoo:balanced:friendly") {
		t.Fatal("only friendly takes a trade that leaves its goal where it is")
	}
}

func TestWaryConfirmsItsOfferOnlyWithPlayersBehindIt(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"wood": 4}
	offer := &Offer{ProposerSeat: 0, Give: map[string]int{"wood": 1}, Get: map[string]int{"ore": 1},
		AcceptedSeats: []int{1, 2}}
	view.Public.Game.TradeOffer = offer
	view.Public.Players[0].VictoryPoints = 4
	view.Public.Players[1].VictoryPoints = 6
	view.Public.Players[2].VictoryPoints = 3

	partner := func(level string) any { return Decide(view, false, level, nil).Payload["partner_seat"] }
	if partner("hard") != 1 || partner("zoo:balanced:wary") != 2 {
		t.Fatalf("hard confirmed %v, wary %v", partner("hard"), partner("zoo:balanced:wary"))
	}
	offer.AcceptedSeats = []int{1}
	offer.DeclinedSeats = []int{2}
	if action := Decide(view, false, "zoo:balanced:wary", nil); action.Name != "cancel_trade" {
		t.Fatalf("wary traded with the leader: %v", action)
	}
}

func TestPersonalitiesOfferAsManyTradesAsTheyMake(t *testing.T) {
	view := cityView()
	view.Private.Resources = map[string]int{"ore": 2, "wheat": 2, "wood": 4, "brick": 4, "sheep": 2}
	view.Public.Game.Bank["ore"] = 10
	view.Public.Game.Log = []string{"red's turn.", "red offers a trade.", "red offers a trade."}

	if action := Decide(view, false, "hard", nil); action.Name != "trade_with_bank" {
		t.Fatalf("hard offered a third trade: %v", action)
	}
	if action := Decide(view, false, "zoo:balanced:friendly", nil); action.Name != "offer_trade" {
		t.Fatalf("friendly stopped at two offers: %v", action)
	}
	view.Public.Game.Log = nil
	if action := Decide(view, false, "zoo:balanced:loner", nil); action.Name != "trade_with_bank" {
		t.Fatalf("the loner offered a trade: %v", action)
	}
}
