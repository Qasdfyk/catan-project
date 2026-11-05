package bot

import (
	"maps"
	"slices"
	"strings"
)

var (
	roadCost    = map[string]int{"wood": 1, "brick": 1}
	devCardCost = map[string]int{"sheep": 1, "wheat": 1, "ore": 1}
)

const (
	maxSettlements = 5
	maxCities      = 4
	maxRoads       = 15
	// cardsOfEach is how many cards of each resource the game has
	cardsOfEach = 19
	// offersPerTurn caps the trades the bot proposes to players in one turn
	offersPerTurn = 2
	// targetReach is how many roads ahead the bot looks for a settlement spot
	targetReach = 3
	// devCardValue is what a development card is worth against a building's 1 + production
	devCardValue = 0.3
)

// goal is what the hard level saves for over the next turns.
type goal struct {
	name string
	cost map[string]int
}

// plan is what the hard level works out once per decision.
type plan struct {
	player
	board *board
	// production is the pips of each resource the bot collects, cities twice
	production map[string]float64
	// scarcity weighs each resource by how rare it is on this board
	scarcity map[string]float64
	// target is the best free corner a few roads away, if there is one
	target     corner
	targetDist int
	hasTarget  bool
	goal       goal
}

func (p player) plan() *plan {
	h := &plan{player: p, board: newBoard(p.View)}
	h.production = h.produces(h.board.mine)
	h.scarcity = scarcity(p.View)
	h.findTarget()
	h.goal = h.chooseGoal()
	return h
}

// produces sums the pips each resource brings a player, leaving out the robbed tile.
func (h *plan) produces(color string) map[string]float64 {
	robber := h.Public.Game.RobberHex
	production := map[string]float64{}
	for _, at := range h.board.corners {
		building, ok := h.board.buildings[at]
		if !ok || building.Owner != color {
			continue
		}
		weight := 1.0
		if building.Type == "city" {
			weight = 2
		}
		for _, tile := range h.board.tiles[at] {
			if tile.Number != nil && (robber == nil || *robber != tile.Hex) {
				production[tile.Resource] += weight * float64(pips(tile.Number))
			}
		}
	}
	return production
}

// scarcity is the average pips of a resource on the board over its own pips,
// so a resource that is rarely rolled counts for more.
func scarcity(view View) map[string]float64 {
	total := map[string]float64{}
	all := 0.0
	for _, tile := range view.Public.Game.BoardTiles {
		if tile.Number != nil {
			total[tile.Resource] += float64(pips(tile.Number))
			all += float64(pips(tile.Number))
		}
	}
	weights := map[string]float64{}
	for _, resource := range resources {
		weights[resource] = 1
		if total[resource] > 0 {
			weights[resource] = min(1.6, max(0.6, all/float64(len(resources))/total[resource]))
		}
	}
	return weights
}

// spotValue rates a corner for a settlement: rare resources, ones the bot
// does not have yet and a port it would use count for more.
func (h *plan) spotValue(at corner) float64 {
	if !h.spots {
		return float64(vertexValue(h.View, h.board.points[at]))
	}
	value := 0.0
	here := map[string]float64{}
	for _, tile := range h.board.tiles[at] {
		if tile.Number == nil {
			continue
		}
		pip := float64(pips(tile.Number))
		have := h.production[tile.Resource]
		value += pip * h.scarcity[tile.Resource] * (1 - min(0.4, have/25))
		if have == 0 && here[tile.Resource] == 0 {
			value += 2
		}
		here[tile.Resource] += pip
	}
	switch port := h.board.ports[at]; {
	case port == "":
	case port == "3:1":
		if slices.Max(slices.Collect(maps.Values(h.Private.TradeRates))) > 3 {
			value += 1.5
		}
	default:
		resource := strings.TrimSuffix(port, "_2:1")
		if h.Private.TradeRates[resource] > 2 {
			value += 0.25 * (h.production[resource] + here[resource])
		}
	}
	return value
}

func (h *plan) count(kind string) int { return countOwn(h.View, kind) }

func (h *plan) roadsBuilt() int {
	built := 0
	for _, color := range h.board.roads {
		if color == h.board.mine {
			built++
		}
	}
	return built
}

// findTarget picks the free corner worth most for the roads it still needs.
func (h *plan) findTarget() {
	if h.count("settlement") >= maxSettlements {
		return
	}
	roadsLeft := maxRoads - h.roadsBuilt()
	dist := h.board.distances(h.board.network(), targetReach)
	best := 0.0
	for _, at := range h.board.corners {
		d, reached := dist[at]
		if !reached || !h.board.free(at) || d > roadsLeft || len(h.board.tiles[at]) == 0 {
			continue
		}
		value := h.spotValue(at) / (1 + 0.5*float64(d))
		if !h.hasTarget || value > best {
			h.target, h.targetDist, h.hasTarget, best = at, d, true, value
		}
	}
}

// turnsFor estimates how many rounds it takes to collect the cost, counting
// what the bank would give for the cards the cost leaves over.
func (h *plan) turnsFor(cost map[string]int) float64 {
	hand := h.Private.Resources
	trades := 0
	for _, resource := range resources {
		if rate := h.Private.TradeRates[resource]; rate > 0 && hand[resource] > cost[resource] {
			trades += (hand[resource] - cost[resource]) / rate
		}
	}
	// The dearest missing cards are the ones to trade for
	var waits []float64
	for _, resource := range resources {
		perRound := float64(len(h.Public.Players)) * h.production[resource] / 36
		for range max(0, cost[resource]-hand[resource]) {
			waits = append(waits, 1/(perRound+0.15))
		}
	}
	slices.Sort(waits)
	turns := 0.0
	for i, wait := range waits {
		if i < len(waits)-trades {
			turns += wait
		}
	}
	return turns
}

func (h *plan) chooseGoal() goal {
	// A card is worth about a third of a point; a building is a point and more cards
	best, bestScore := goal{"dev_card", devCardCost}, devCardValue/(1+h.turnsFor(devCardCost))
	consider := func(name string, cost map[string]int, value float64) {
		if score := value / (1 + h.turnsFor(cost)); score > bestScore {
			best, bestScore = goal{name, cost}, score
		}
	}
	if h.count("settlement") > 0 && h.count("city") < maxCities {
		top := 0.0
		for _, at := range h.board.corners {
			if building, ok := h.board.buildings[at]; ok && building.Owner == h.board.mine && building.Type == "settlement" {
				top = max(top, h.spotValue(at))
			}
		}
		consider("city", cityCost, 1+top/10)
	}
	if h.hasTarget {
		cost := maps.Clone(settlementCost)
		for resource, amount := range roadCost {
			cost[resource] += amount * h.targetDist
		}
		consider("settlement", cost, 1+h.spotValue(h.target)/10)
	}
	return best
}

// missing counts the cards of the goal the hand lacks.
func missing(cost, hand map[string]int) int {
	total := 0
	for _, resource := range resources {
		total += max(0, cost[resource]-hand[resource])
	}
	return total
}

func pay(hand, cost map[string]int) map[string]int {
	left := maps.Clone(hand)
	for resource, amount := range cost {
		left[resource] -= amount
	}
	return left
}

// spares says if buying this leaves the goal no further away.
func (h *plan) spares(cost map[string]int) bool {
	hand := h.Private.Resources
	return missing(h.goal.cost, pay(hand, cost)) <= missing(h.goal.cost, hand)
}

func (p player) hardMain() *Action {
	legal := p.Private.Legal
	if offer := p.Public.Game.TradeOffer; offer != nil && offer.ProposerSeat == p.Private.Seat {
		return p.followOffer(offer)
	}
	h := p.plan()

	switch {
	case len(legal.Cities) > 0:
		return &Action{"upgrade_city", position(h.best(legal.Cities))}
	case len(legal.Settlements) > 0:
		return &Action{"build_settlement", position(h.best(legal.Settlements))}
	}
	if card := h.playCard(); card != nil {
		return card
	}
	if len(legal.Roads) > 0 {
		if road, ok := h.roadToward(legal.Roads); ok && (h.goal.name == "settlement" || h.spares(roadCost)) {
			return &Action{"build_road", position(road)}
		}
		if road, ok := h.longestRoadEdge(legal.Roads); ok {
			return &Action{"build_road", position(road)}
		}
	}
	if legal.CanBuyDevCard && (h.goal.name == "dev_card" || h.spares(devCardCost)) {
		return &Action{"buy_dev_card", nil}
	}
	if trade := h.trade(); trade != nil {
		return trade
	}
	if sum(p.Private.Resources) > p.discardLimit() {
		if spend := h.shed(); spend != nil {
			return spend
		}
	}
	return &Action{"end_turn", nil}
}

func (p player) discardLimit() int {
	if limit := p.Public.Settings.DiscardLimit; limit > 0 {
		return limit
	}
	return 7
}

// best is the most valuable corner among the options, the first on a tie.
func (h *plan) best(options []Position) Position {
	best, bestValue := options[0], -1.0
	for _, option := range options {
		if value := h.spotValue(cornerOf(option.vertex())); value > bestValue {
			best, bestValue = option, value
		}
	}
	return best
}

// roadToward is the road that brings the target one step closer.
func (h *plan) roadToward(options []Position) (Position, bool) {
	if !h.hasTarget || h.targetDist == 0 {
		return Position{}, false
	}
	back := h.board.distances([]corner{h.target}, targetReach+1)
	network := map[corner]bool{}
	for _, at := range h.board.network() {
		network[at] = true
	}
	var best Position
	found := false
	bestDist := h.targetDist
	for _, option := range options {
		for _, end := range option.side() {
			if d, ok := back[end]; ok && !network[end] && d < bestDist {
				best, bestDist, found = option, d, true
			}
		}
	}
	return best, found
}

// longestRoadEdge is a road that brings the bot within reach of the Longest
// Road, if the hard level is going for it and the road is worth its cards.
func (h *plan) longestRoadEdge(options []Position) (Position, bool) {
	if !h.longestRoad {
		return Position{}, false
	}
	mine := h.board.longestRoad(nil)
	holder := 4
	for _, player := range h.Public.Players {
		if player.Color == h.Public.Game.LongestRoadHolder {
			if player.Color == h.board.mine {
				return Position{}, false
			}
			holder = max(holder, player.RoadLength)
		}
	}
	// Close means two roads or fewer from taking it
	if mine+2 <= holder {
		return Position{}, false
	}
	var best Position
	bestLength := mine
	for _, option := range options {
		edge := option.side()
		if length := h.board.longestRoad(&edge); length > bestLength {
			best, bestLength = option, length
		}
	}
	if bestLength == mine {
		return Position{}, false
	}
	// A road that takes the card is always worth it; one on the way only from spare cards
	return best, bestLength > holder || h.spares(roadCost)
}
