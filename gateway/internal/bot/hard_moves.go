package bot

import (
	"maps"
	"slices"
	"strings"
)

func (p player) hardSetup() *Action {
	legal := p.Private.Legal
	h := p.plan()
	if len(legal.Settlements) > 0 {
		return &Action{"build_settlement", position(h.best(legal.Settlements))}
	}
	return &Action{"build_road", position(h.lookAhead(legal.Roads))}
}

// lookAhead is the road leading to the best free corner within two more roads.
func (h *plan) lookAhead(options []Position) Position {
	best, bestValue := options[0], -1.0
	for _, option := range options {
		for _, end := range option.side() {
			for at, d := range h.board.distances([]corner{end}, 2) {
				if !h.board.free(at) {
					continue
				}
				value := h.spotValue(at) / (1 + 0.5*float64(d+1))
				if value > bestValue {
					best, bestValue = option, value
				}
			}
		}
	}
	return best
}

func (p player) hardRoad() *Action {
	legal := p.Private.Legal
	h := p.plan()
	if road, ok := h.roadToward(legal.Roads); ok {
		return &Action{"build_road", position(road)}
	}
	if road, ok := h.longestRoadEdge(legal.Roads); ok {
		return &Action{"build_road", position(road)}
	}
	return &Action{"build_road", position(h.lookAhead(legal.Roads))}
}

func (h *plan) playCard() *Action {
	playable := h.Private.Legal.PlayableDevCards
	if len(playable) == 0 {
		return nil
	}
	hand := h.Private.Resources
	knight := slices.Contains(playable, "knight")
	if knight && (robberOnMyTile(h.View) || h.armyWithinReach()) {
		return &Action{"play_knight", nil}
	}
	if slices.Contains(playable, "monopoly") {
		if resource, taken := h.monopoly(); taken >= 3 {
			return &Action{"play_monopoly", map[string]any{"resource": resource}}
		}
	}
	if slices.Contains(playable, "year_of_plenty") {
		var wanted []string
		bank := maps.Clone(h.Public.Game.Bank)
		for _, resource := range resources {
			for range max(0, h.goal.cost[resource]-hand[resource]) {
				if bank[resource] > 0 && len(wanted) < 2 {
					bank[resource]--
					wanted = append(wanted, resource)
				}
			}
		}
		if len(wanted) == 1 && bank[wanted[0]] > 0 {
			wanted = append(wanted, wanted[0])
		}
		if len(wanted) == 2 {
			return &Action{"play_year_of_plenty", map[string]any{"first": wanted[0], "second": wanted[1]}}
		}
	}
	if slices.Contains(playable, "road_building") && len(h.Private.Legal.Roads) > 0 {
		if _, ok := h.roadToward(h.Private.Legal.Roads); ok {
			return &Action{"play_road_building", nil}
		}
		if _, ok := h.longestRoadEdge(h.Private.Legal.Roads); ok {
			return &Action{"play_road_building", nil}
		}
	}
	if knight {
		return &Action{"play_knight", nil}
	}
	return nil
}

// armyWithinReach says if one more knight gives the bot the Largest Army.
func (h *plan) armyWithinReach() bool {
	me := h.Public.Players[h.Private.Seat]
	if h.Public.Game.LargestArmyHolder == me.Color {
		return false
	}
	needed := 3
	for _, player := range h.Public.Players {
		if player.Color == h.Public.Game.LargestArmyHolder {
			needed = player.KnightsPlayed + 1
		}
	}
	return me.KnightsPlayed+1 >= needed
}

// monopoly names the resource that takes most, and how many the others
// probably hold: whatever is neither in the bank nor in the bot's hand.
func (h *plan) monopoly() (string, int) {
	hand := h.Private.Resources
	best, bestWorth, taken := "", -1, 0
	for _, resource := range resources {
		held := max(0, cardsOfEach-h.Public.Game.Bank[resource]-hand[resource])
		worth := held
		if hand[resource] < h.goal.cost[resource] {
			worth *= 2
		}
		if worth > bestWorth {
			best, bestWorth, taken = resource, worth, held
		}
	}
	return best, taken
}

// trade asks the players, then the bank, for a card the goal still needs,
// giving only cards the goal leaves over.
func (h *plan) trade() *Action {
	hand := h.Private.Resources
	cost := h.goal.cost
	var wanted []string
	for _, resource := range resources {
		if hand[resource] < cost[resource] {
			wanted = append(wanted, resource)
		}
	}
	if len(wanted) == 0 {
		return nil
	}
	// The resource the bot rolls least is the hardest to get on its own
	slices.SortStableFunc(wanted, func(a, b string) int {
		return int(h.production[a] - h.production[b])
	})
	spare := slices.Clone(resources)
	slices.SortStableFunc(spare, func(a, b string) int {
		return (hand[b] - cost[b]) - (hand[a] - cost[a])
	})

	if h.offers {
		var offers [][2]string
		for _, want := range wanted {
			// Only worth asking when the others hold some
			if cardsOfEach-h.Public.Game.Bank[want]-hand[want] < 2 {
				continue
			}
			for _, give := range spare {
				if hand[give]-cost[give] >= 1 && h.Private.TradeRates[give] > 2 {
					offers = append(offers, [2]string{give, want})
				}
			}
		}
		if made := h.offersMade(); made < offersPerTurn && made < len(offers) {
			offer := offers[made]
			return &Action{"offer_trade", map[string]any{
				"give": map[string]int{offer[0]: 1}, "get": map[string]int{offer[1]: 1},
			}}
		}
	}
	for _, want := range wanted {
		if h.Public.Game.Bank[want] == 0 {
			continue
		}
		for _, give := range spare {
			if rate := h.Private.TradeRates[give]; rate > 0 && hand[give]-cost[give] >= rate {
				return &Action{"trade_with_bank", map[string]any{"give": give, "get": want}}
			}
		}
	}
	return nil
}

// offersMade counts the bot's offers since its turn began, from the game log.
func (h *plan) offersMade() int {
	name := h.Public.Players[h.Private.Seat].Name
	made := 0
	for _, line := range slices.Backward(h.Public.Game.Log) {
		if strings.HasSuffix(line, "'s turn.") {
			break
		}
		if line == name+" offers a trade." {
			made++
		}
	}
	return made
}

// followOffer waits for everyone to answer, so no answer comes after the
// offer is gone, then confirms the first player to accept or withdraws it.
func (p player) followOffer(offer *Offer) *Action {
	if len(offer.AcceptedSeats)+len(offer.DeclinedSeats) < len(p.Public.Players)-1 {
		return nil
	}
	if len(offer.AcceptedSeats) > 0 && missing(offer.Give, p.Private.Resources) == 0 {
		return &Action{"confirm_trade", map[string]any{"partner_seat": offer.AcceptedSeats[0]}}
	}
	return &Action{"cancel_trade", nil}
}

// shed spends cards before ending a turn with more than a 7 would leave.
func (h *plan) shed() *Action {
	legal := h.Private.Legal
	if legal.CanBuyDevCard {
		return &Action{"buy_dev_card", nil}
	}
	if len(legal.Roads) > 0 {
		if road, ok := h.roadToward(legal.Roads); ok {
			return &Action{"build_road", position(road)}
		}
		return &Action{"build_road", position(h.lookAhead(legal.Roads))}
	}
	return nil
}

// hardDiscard gives up what the goal does not need first.
func (p player) hardDiscard() *Action {
	h := p.plan()
	hand := maps.Clone(p.Private.Resources)
	cards := map[string]int{}
	for range p.Private.Legal.MustDiscard {
		largest := ""
		for _, resource := range resources {
			if hand[resource] == 0 {
				continue
			}
			extra := hand[resource] - h.goal.cost[resource]
			if largest == "" || extra > hand[largest]-h.goal.cost[largest] {
				largest = resource
			}
		}
		hand[largest]--
		cards[largest]++
	}
	return &Action{"discard", map[string]any{"cards": cards}}
}

// threat weighs an opponent by points, most of all the leader and anyone
// close to winning.
func (p player) threat(seat int) int {
	points := p.Public.Players[seat].VictoryPoints
	lead := 0
	for _, player := range p.Public.Players {
		if player.Seat != p.Private.Seat {
			lead = max(lead, player.VictoryPoints)
		}
	}
	weight := 1 + points
	if points == lead {
		weight += 2
	}
	if points+3 >= p.victoryPoints() {
		weight += 4
	}
	return weight
}

func (p player) victoryPoints() int {
	if points := p.Public.Settings.VictoryPoints; points > 0 {
		return points
	}
	return 10
}

// hardRobber blocks the tile that costs the leaders most, never one of its own.
func (p player) hardRobber() Hex {
	seats := map[string]Player{}
	for _, player := range p.Public.Players {
		seats[player.Color] = player
	}
	mine := p.Public.Players[p.Private.Seat].Color
	numbers := map[Hex]*int{}
	for _, tile := range p.Public.Game.BoardTiles {
		numbers[tile.Hex] = tile.Number
	}
	var best Hex
	bestHarm, found := 0, false
	for _, option := range p.Private.Legal.RobberHexes {
		center := option.center()
		harm, own, victims := 0, false, false
		for _, building := range p.Public.Game.Settlements {
			if !touches(center, building.vertex()) {
				continue
			}
			if building.Owner == mine {
				own = true
				break
			}
			owner := seats[building.Owner]
			weight := p.threat(owner.Seat) * (pips(numbers[option]) + 1)
			if building.Type == "city" {
				weight *= 2
			}
			harm += weight
			victims = victims || owner.CardCount > 0
		}
		if own {
			continue
		}
		if victims {
			harm += 3
		}
		if !found || harm > bestHarm {
			best, bestHarm, found = option, harm, true
		}
	}
	if !found {
		return p.robberHex()
	}
	return best
}

// hardVictim robs the leader, the one with more cards on a tie.
func (p player) hardVictim() int {
	targets := slices.Clone(p.Private.Legal.StealTargets)
	score := func(seat int) int {
		return 2*p.threat(seat) + p.Public.Players[seat].CardCount
	}
	slices.SortStableFunc(targets, func(a, b int) int { return score(b) - score(a) })
	return targets[0]
}

// hardAnswer takes an offer that brings its goal closer, unless it would
// help the leader or someone about to win.
func (p player) hardAnswer() *Action {
	offer := p.Public.Game.TradeOffer
	seat := p.Private.Seat
	if offer == nil || offer.ProposerSeat == seat ||
		slices.Contains(offer.AcceptedSeats, seat) || slices.Contains(offer.DeclinedSeats, seat) {
		return nil
	}
	hand := p.Private.Resources
	accept := missing(offer.Get, hand) == 0

	proposer := p.Public.Players[offer.ProposerSeat]
	leads := true
	for _, player := range p.Public.Players {
		if player.Seat != proposer.Seat && player.VictoryPoints >= proposer.VictoryPoints {
			leads = false
		}
	}
	if leads || proposer.VictoryPoints+2 >= p.victoryPoints() {
		accept = false
	}
	if accept {
		h := p.plan()
		after := pay(hand, offer.Get)
		for resource, amount := range offer.Give {
			after[resource] += amount
		}
		accept = missing(h.goal.cost, after) < missing(h.goal.cost, hand)
	}
	return &Action{"respond_trade", map[string]any{"accept": accept}}
}
