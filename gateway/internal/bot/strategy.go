package bot

import (
	"maps"
	"math/rand/v2"
	"slices"
	"sort"
)

var (
	settlementCost = map[string]int{"wood": 1, "brick": 1, "wheat": 1, "sheep": 1}
	cityCost       = map[string]int{"ore": 3, "wheat": 2}
	resources      = []string{"wood", "brick", "sheep", "wheat", "ore"}
)

// style is how one level plays. Every level chooses among the same legal
// moves; a level only changes how carefully it chooses.
type style struct {
	// spotChoices picks randomly among this many of the best places to build
	spotChoices int
	// randomRobber moves the robber and steals without looking
	randomRobber bool
	// defensiveKnight plays a knight before rolling to free its own tile
	defensiveKnight bool
	// cardChance is the chance to play a card when one is playable
	cardChance float64
	// tradeFrom trades with the bank only when holding this many cards
	tradeFrom int
}

var styles = map[string]style{
	"easy":   {spotChoices: 3, randomRobber: true, cardChance: 0.3, tradeFrom: 8},
	"medium": {spotChoices: 1, defensiveKnight: true, cardChance: 1},
	// Plays as medium until it gets its own heuristics
	"hard": {spotChoices: 1, defensiveKnight: true, cardChance: 1},
}

// DefaultLevel is used for a seat with no level or an unknown one.
const DefaultLevel = "medium"

// player is one decision: what the seat sees, how it plays and its dice.
type player struct {
	View
	style
	rng *rand.Rand
}

// Decide returns the seat's next action, or nil if it has nothing to do.
// With fallback set the bot only does what cannot fail, to get out of a
// situation where the server refused its plan. Levels that leave things to
// chance draw from rng; nil stands for a fixed seed.
func Decide(view View, fallback bool, level string, rng *rand.Rand) *Action {
	game := view.Public.Game
	legal := view.Private.Legal
	if game == nil || legal == nil || game.IsGameOver {
		return nil
	}
	look, ok := styles[level]
	if !ok {
		look = styles[DefaultLevel]
	}
	if rng == nil {
		rng = rand.New(rand.NewPCG(1, 2))
	}
	p := player{view, look, rng}

	if legal.MustDiscard > 0 {
		return discard(view)
	}
	if answer := answerOffer(view); answer != nil {
		return answer
	}
	if game.CurrentSeat != view.Private.Seat {
		return nil
	}

	switch game.TurnPhase {
	case "setup":
		if len(legal.Settlements) > 0 {
			return &Action{"build_settlement", position(p.vertex(legal.Settlements))}
		}
		return &Action{"build_road", position(p.road(legal.Roads))}
	case "roll_dice":
		if !fallback && p.defensiveKnight && robberOnMyTile(view) && slices.Contains(legal.PlayableDevCards, "knight") {
			return &Action{"play_knight", nil}
		}
		return &Action{"roll_dice", nil}
	case "move_robber":
		return &Action{"move_robber", map[string]any{"hex": p.robberHex()}}
	case "steal":
		return &Action{"steal", map[string]any{"victim_seat": p.victim()}}
	case "road_building":
		return &Action{"build_road", position(p.road(legal.Roads))}
	case "main_phase":
		if fallback {
			return &Action{"end_turn", nil}
		}
		return p.mainPhase()
	}
	return nil
}

func (p player) mainPhase() *Action {
	legal := p.Private.Legal
	hand := p.Private.Resources

	switch {
	case len(legal.Cities) > 0:
		return &Action{"upgrade_city", position(p.vertex(legal.Cities))}
	case len(legal.Settlements) > 0:
		return &Action{"build_settlement", position(p.vertex(legal.Settlements))}
	}

	if p.cardChance >= 1 || p.rng.Float64() < p.cardChance {
		if card := playCard(p.View); card != nil {
			return card
		}
	}

	if legal.CanBuyDevCard {
		return &Action{"buy_dev_card", nil}
	}
	if len(legal.Roads) > 0 && countOwn(p.View, "settlement")+countOwn(p.View, "city") < 9 {
		return &Action{"build_road", position(p.road(legal.Roads))}
	}
	if sum(hand) >= p.tradeFrom {
		if trade := bankTrade(p.View, hand); trade != nil {
			return trade
		}
	}
	return &Action{"end_turn", nil}
}

func playCard(view View) *Action {
	playable := view.Private.Legal.PlayableDevCards
	hand := view.Private.Resources
	switch {
	case slices.Contains(playable, "monopoly"):
		return &Action{"play_monopoly", map[string]any{"resource": scarcest(hand, cityCost)}}
	case slices.Contains(playable, "year_of_plenty"):
		wanted := scarcest(hand, settlementCost)
		if view.Public.Game.Bank[wanted] >= 2 {
			return &Action{"play_year_of_plenty", map[string]any{"first": wanted, "second": wanted}}
		}
	case slices.Contains(playable, "road_building") && len(view.Private.Legal.Roads) > 0:
		return &Action{"play_road_building", nil}
	case slices.Contains(playable, "knight"):
		return &Action{"play_knight", nil}
	}
	return nil
}

// bankTrade gives away only what the next building does not need.
func bankTrade(view View, hand map[string]int) *Action {
	goal := cityCost
	if countOwn(view, "settlement") == 0 {
		goal = settlementCost
	}
	missing := ""
	for _, resource := range resources {
		if hand[resource] < goal[resource] && view.Public.Game.Bank[resource] > 0 {
			missing = resource
			break
		}
	}
	if missing == "" {
		return nil
	}
	for _, resource := range resources {
		rate := view.Private.TradeRates[resource]
		if rate > 0 && hand[resource]-goal[resource] >= rate {
			return &Action{"trade_with_bank", map[string]any{"give": resource, "get": missing}}
		}
	}
	return nil
}

func answerOffer(view View) *Action {
	offer := view.Public.Game.TradeOffer
	seat := view.Private.Seat
	if offer == nil || offer.ProposerSeat == seat ||
		slices.Contains(offer.AcceptedSeats, seat) || slices.Contains(offer.DeclinedSeats, seat) {
		return nil
	}

	hand := view.Private.Resources
	accept := sum(offer.Give) >= sum(offer.Get)
	for resource, amount := range offer.Get {
		// Keeps at least one of everything it gives away
		accept = accept && hand[resource] > amount
	}
	return &Action{"respond_trade", map[string]any{"accept": accept}}
}

func discard(view View) *Action {
	hand := maps.Clone(view.Private.Resources)
	cards := map[string]int{}
	for range view.Private.Legal.MustDiscard {
		largest := resources[0]
		for _, resource := range resources {
			if hand[resource] > hand[largest] {
				largest = resource
			}
		}
		hand[largest]--
		cards[largest]++
	}
	return &Action{"discard", map[string]any{"cards": cards}}
}

func position(p Position) map[string]any {
	return map[string]any{"hex": p.Hex, "direction": p.Direction}
}

// vertexValue sums the production of the tiles around a point, and rewards
// variety and the resources for cities.
func vertexValue(view View, at point) int {
	value := 0
	seen := map[string]bool{}
	for _, tile := range view.Public.Game.BoardTiles {
		if !touches(tile.Hex.center(), at) || tile.Number == nil {
			continue
		}
		value += 2 * pips(tile.Number)
		if !seen[tile.Resource] {
			seen[tile.Resource] = true
			value += 3
		}
		if tile.Resource == "ore" || tile.Resource == "wheat" {
			value++
		}
	}
	return value
}

func (p player) vertex(options []Position) Position {
	values := make([]int, len(options))
	for i, option := range options {
		values[i] = vertexValue(p.View, option.vertex())
	}
	return p.choose(options, values)
}

// road heads for the most productive corner where a settlement could stand.
func (p player) road(options []Position) Position {
	values := make([]int, len(options))
	for i, option := range options {
		values[i] = -1
		for _, end := range option.edgeEnds() {
			if buildable(p.View, end) {
				values[i] = max(values[i], vertexValue(p.View, end))
			}
		}
	}
	return p.choose(options, values)
}

// choose takes one of the spotChoices best options. Ties keep their order, so
// with one choice it is the first of the best.
func (p player) choose(options []Position, values []int) Position {
	order := make([]int, len(options))
	for i := range order {
		order[i] = i
	}
	sort.SliceStable(order, func(i, j int) bool { return values[order[i]] > values[order[j]] })
	if top := min(p.spotChoices, len(order)); top > 1 {
		return options[order[p.rng.IntN(top)]]
	}
	return options[order[0]]
}

func buildable(view View, at point) bool {
	for _, building := range view.Public.Game.Settlements {
		spot := building.vertex()
		if same(spot, at) || touches(spot, at) {
			return false
		}
	}
	return true
}

func robberOnMyTile(view View) bool {
	game := view.Public.Game
	if game.RobberHex == nil {
		return false
	}
	return tileHarm(view, *game.RobberHex) < 0
}

// tileHarm is positive if the robber on this tile hurts opponents more than the bot.
func tileHarm(view View, hex Hex) int {
	number := (*int)(nil)
	for _, tile := range view.Public.Game.BoardTiles {
		if tile.Hex == hex {
			number = tile.Number
		}
	}
	mine := view.Public.Players[view.Private.Seat].Color
	center := hex.center()
	harm := 0
	for _, building := range view.Public.Game.Settlements {
		if !touches(center, building.vertex()) {
			continue
		}
		weight := 1
		if building.Type == "city" {
			weight = 2
		}
		if building.Owner == mine {
			weight *= -2
		}
		harm += weight * (pips(number) + 1)
	}
	return harm
}

func (p player) robberHex() Hex {
	options := p.Private.Legal.RobberHexes
	if p.randomRobber {
		return options[p.rng.IntN(len(options))]
	}
	best, bestHarm := options[0], tileHarm(p.View, options[0])
	for _, option := range options[1:] {
		if harm := tileHarm(p.View, option); harm > bestHarm {
			best, bestHarm = option, harm
		}
	}
	return best
}

// victim is the player with the most cards, or anyone for a careless robber.
func (p player) victim() int {
	targets := slices.Clone(p.Private.Legal.StealTargets)
	if p.randomRobber {
		return targets[p.rng.IntN(len(targets))]
	}
	sort.Slice(targets, func(i, j int) bool {
		a, b := p.Public.Players[targets[i]], p.Public.Players[targets[j]]
		return a.CardCount > b.CardCount
	})
	return targets[0]
}

func scarcest(hand map[string]int, among map[string]int) string {
	best := ""
	for _, resource := range resources {
		if _, wanted := among[resource]; wanted && (best == "" || hand[resource] < hand[best]) {
			best = resource
		}
	}
	return best
}

func countOwn(view View, kind string) int {
	mine := view.Public.Players[view.Private.Seat].Color
	count := 0
	for _, building := range view.Public.Game.Settlements {
		if building.Owner == mine && building.Type == kind {
			count++
		}
	}
	return count
}

func sum(cards map[string]int) int {
	total := 0
	for _, amount := range cards {
		total += amount
	}
	return total
}
