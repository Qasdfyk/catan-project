// Package bot plays Catan as an ordinary client. It only chooses among the
// moves the server calls legal, so no game rule is repeated here.
package bot

import "math"

type Hex struct {
	Q int `json:"q"`
	R int `json:"r"`
	S int `json:"s"`
}

type Position struct {
	Hex       Hex `json:"hex"`
	Direction int `json:"direction"`
}

type Tile struct {
	Hex      Hex    `json:"hex"`
	Resource string `json:"resource"`
	Number   *int   `json:"number"`
}

type Building struct {
	Position
	Owner string `json:"owner"`
	Type  string `json:"type"`
}

type Player struct {
	Seat          int    `json:"seat"`
	Name          string `json:"name"`
	Color         string `json:"color"`
	VictoryPoints int    `json:"victory_points"`
	CardCount     int    `json:"card_count"`
	RoadLength    int    `json:"road_length"`
	KnightsPlayed int    `json:"knights_played"`
}

type Road struct {
	Position
	Color string `json:"color"`
}

type Port struct {
	Type     string     `json:"type"`
	Vertices []Position `json:"vertices"`
}

type Offer struct {
	ProposerSeat  int            `json:"proposer_seat"`
	Give          map[string]int `json:"give"`
	Get           map[string]int `json:"get"`
	AcceptedSeats []int          `json:"accepted_seats"`
	DeclinedSeats []int          `json:"declined_seats"`
}

type Game struct {
	TurnPhase   string         `json:"turn_phase"`
	CurrentSeat int            `json:"current_seat"`
	IsGameOver  bool           `json:"is_game_over"`
	WinnerSeat  *int           `json:"winner_seat"`
	RobberHex   *Hex           `json:"robber_hex"`
	BoardTiles  []Tile         `json:"board_tiles"`
	Settlements []Building     `json:"settlements"`
	Roads       []Road         `json:"roads"`
	Ports       []Port         `json:"ports"`
	Bank        map[string]int `json:"bank"`
	TradeOffer  *Offer         `json:"trade_offer"`
	Log         []string       `json:"log"`
	// Colors of the players holding the bonus cards, or empty
	LongestRoadHolder string `json:"longest_road_holder"`
	LargestArmyHolder string `json:"largest_army_holder"`
}

type Settings struct {
	VictoryPoints int `json:"victory_points"`
	DiscardLimit  int `json:"discard_limit"`
}

type Public struct {
	Version  int      `json:"version"`
	Status   string   `json:"status"`
	Settings Settings `json:"settings"`
	Players  []Player `json:"players"`
	Game     *Game    `json:"game"`
}

type Legal struct {
	Settlements      []Position `json:"settlements"`
	Roads            []Position `json:"roads"`
	Cities           []Position `json:"cities"`
	RobberHexes      []Hex      `json:"robber_hexes"`
	StealTargets     []int      `json:"steal_targets"`
	MustDiscard      int        `json:"must_discard"`
	CanBuyDevCard    bool       `json:"can_buy_dev_card"`
	PlayableDevCards []string   `json:"playable_dev_cards"`
}

type Private struct {
	Seat       int            `json:"seat"`
	Resources  map[string]int `json:"resources"`
	DevCards   []string       `json:"dev_cards"`
	TradeRates map[string]int `json:"trade_rates"`
	Legal      *Legal         `json:"legal"`
}

// View is what one seat can see of the game.
type View struct {
	Public  Public  `json:"public"`
	Private Private `json:"private"`
}

// Action is a message for the server.
type Action struct {
	Name    string         `json:"name"`
	Payload map[string]any `json:"payload"`
}

// The geometry below only compares distances, in units of one hex side.
type point struct{ x, y float64 }

func (h Hex) center() point {
	return point{math.Sqrt(3) * (float64(h.Q) + float64(h.R)/2), 1.5 * float64(h.R)}
}

func (p Position) vertex() point {
	center := p.Hex.center()
	angle := (float64(60*p.Direction) - 30) * math.Pi / 180
	return point{center.x + math.Cos(angle), center.y + math.Sin(angle)}
}

// edgeEnds returns both vertices of an edge, which is identified like a vertex.
func (p Position) edgeEnds() [2]point {
	return [2]point{p.vertex(), Position{p.Hex, (p.Direction + 1) % 6}.vertex()}
}

func distance(a, b point) float64 {
	return math.Hypot(a.x-b.x, a.y-b.y)
}

// touches also holds a hex center and its corner, which lie one side apart.
func touches(a, b point) bool {
	return math.Abs(distance(a, b)-1) < 0.01
}

func same(a, b point) bool {
	return distance(a, b) < 0.01
}

// pips is how many of the 36 dice combinations produce the number.
func pips(number *int) int {
	if number == nil {
		return 0
	}
	if *number > 7 {
		return 13 - *number
	}
	return *number - 1
}
