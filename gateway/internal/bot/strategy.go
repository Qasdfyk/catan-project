package bot

import (
	"maps"
	"slices"
	"sort"
)

var (
	settlementCost = map[string]int{"wood": 1, "brick": 1, "wheat": 1, "sheep": 1}
	cityCost       = map[string]int{"ore": 3, "wheat": 2}
	resources      = []string{"wood", "brick", "sheep", "wheat", "ore"}
)

// Decide returns the seat's next action, or nil if it has nothing to do.
// With fallback set the bot only does what cannot fail, to get out of a
// situation where the server refused its plan.
func Decide(view View, fallback bool) *Action {
	game := view.Public.Game
	legal := view.Private.Legal
	if game == nil || legal == nil || game.IsGameOver {
		return nil
	}

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
			return &Action{"build_settlement", position(bestVertex(view, legal.Settlements))}
		}
		return &Action{"build_road", position(bestRoad(view, legal.Roads))}
	case "roll_dice":
		if !fallback && robberOnMyTile(view) && slices.Contains(legal.PlayableDevCards, "knight") {
			return &Action{"play_knight", nil}
		}
		return &Action{"roll_dice", nil}
	case "move_robber":
		return &Action{"move_robber", map[string]any{"hex": bestRobberHex(view)}}
	case "steal":
		return &Action{"steal", map[string]any{"victim_seat": richestTarget(view)}}
	case "road_building":
		return &Action{"build_road", position(bestRoad(view, legal.Roads))}
	case "main_phase":
		if fallback {
			return &Action{"end_turn", nil}
		}
		return mainPhase(view)
	}
	return nil
}

func mainPhase(view View) *Action {
	legal := view.Private.Legal
	hand := view.Private.Resources

	switch {
	case len(legal.Cities) > 0:
		return &Action{"upgrade_city", position(bestVertex(view, legal.Cities))}
	case len(legal.Settlements) > 0:
		return &Action{"build_settlement", position(bestVertex(view, legal.Settlements))}
	}

	if card := playCard(view); card != nil {
		return card
	}

	if legal.CanBuyDevCard {
		return &Action{"buy_dev_card", nil}
	}
	if len(legal.Roads) > 0 && countOwn(view, "settlement")+countOwn(view, "city") < 9 {
		return &Action{"build_road", position(bestRoad(view, legal.Roads))}
	}
	if trade := bankTrade(view, hand); trade != nil {
		return trade
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

func bestVertex(view View, options []Position) Position {
	best, bestValue := options[0], -1
	for _, option := range options {
		if value := vertexValue(view, option.vertex()); value > bestValue {
			best, bestValue = option, value
		}
	}
	return best
}

// bestRoad heads for the most productive corner where a settlement could stand.
func bestRoad(view View, options []Position) Position {
	best, bestValue := options[0], -1
	for _, option := range options {
		for _, end := range option.edgeEnds() {
			if !buildable(view, end) {
				continue
			}
			if value := vertexValue(view, end); value > bestValue {
				best, bestValue = option, value
			}
		}
	}
	return best
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

func bestRobberHex(view View) Hex {
	options := view.Private.Legal.RobberHexes
	best, bestHarm := options[0], tileHarm(view, options[0])
	for _, option := range options[1:] {
		if harm := tileHarm(view, option); harm > bestHarm {
			best, bestHarm = option, harm
		}
	}
	return best
}

func richestTarget(view View) int {
	targets := slices.Clone(view.Private.Legal.StealTargets)
	sort.Slice(targets, func(i, j int) bool {
		a, b := view.Public.Players[targets[i]], view.Public.Players[targets[j]]
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
