package bot

import (
	"math"
	"math/rand/v2"
	"strconv"
	"strings"
)

// The zoo is the hard level with its judgement turned by weights, so that
// bots playing each other produce games of many styles instead of one. An
// archetype sets what the bot builds toward, a personality how it trades,
// and a seed shakes every weight a little, so no two games are played by
// exactly the same bot. The level "zoo:balanced:fair" with no seed is the
// hard level itself.
//
// A zoo level is written "zoo:<archetype>:<personality>[:<seed>]", for
// example "zoo:ore-wheat:friendly:1234".

// weights tune what the hard level values. At 1 a weight leaves the hard
// level as it is.
type weights struct {
	// Resource multiplies the pips of each resource in a building spot
	Resource map[string]float64 `json:"resource"`
	// Variety scales the bonus for a resource the bot does not collect yet
	// and the discount for more of one it already has
	Variety float64 `json:"variety"`
	// Port scales the bonus of a port the bot would use
	Port float64 `json:"port"`
	// City, Settlement and DevCard scale what each goal is worth
	City       float64 `json:"city"`
	Settlement float64 `json:"settlement"`
	DevCard    float64 `json:"dev_card"`
	// RoadReach is how many roads behind the Longest Road the bot still
	// builds for it
	RoadReach int `json:"road_reach"`
}

// personality is how a bot trades with players.
type personality struct {
	// Offers is how many trades it proposes to players in one turn
	Offers int `json:"offers_per_turn"`
	// Accepts says if it answers yes to anything at all
	Accepts bool `json:"accepts"`
	// Neutral takes an offer that leaves its goal no further away; without
	// it the offer must bring the goal closer
	Neutral bool `json:"neutral"`
	// Embargo: 0 trades with anyone, 1 refuses the leader and anyone close
	// to winning, 2 also refuses anyone ahead of itself and never confirms
	// its own offer with them
	Embargo int `json:"embargo"`
}

var archetypes = map[string]weights{
	"balanced": {
		Resource: map[string]float64{"wood": 1, "brick": 1, "sheep": 1, "wheat": 1, "ore": 1},
		Variety:  1, Port: 1, City: 1, Settlement: 1, DevCard: 1, RoadReach: 2,
	},
	// Cities and development cards: ore and wheat, few roads
	"ore-wheat": {
		Resource: map[string]float64{"wood": 0.75, "brick": 0.75, "sheep": 1.1, "wheat": 1.3, "ore": 1.4},
		Variety:  0.8, Port: 1, City: 1.3, Settlement: 0.9, DevCard: 1.6, RoadReach: 1,
	},
	// Spread out: wood and brick, settlements and the Longest Road
	"wood-brick": {
		Resource: map[string]float64{"wood": 1.4, "brick": 1.4, "sheep": 1, "wheat": 1, "ore": 0.7},
		Variety:  0.8, Port: 1, City: 0.85, Settlement: 1.3, DevCard: 0.6, RoadReach: 3,
	},
	// Lots of one resource and the port that sells it
	"port": {
		Resource: map[string]float64{"wood": 1, "brick": 1, "sheep": 1, "wheat": 1, "ore": 1},
		Variety:  0.3, Port: 3, City: 1, Settlement: 1.1, DevCard: 0.9, RoadReach: 2,
	},
}

var personalities = map[string]personality{
	"fair":     {Offers: 2, Accepts: true, Embargo: 1},
	"friendly": {Offers: 3, Accepts: true, Neutral: true, Embargo: 0},
	"wary":     {Offers: 1, Accepts: true, Embargo: 2},
	"loner":    {Offers: 0, Accepts: false, Embargo: 2},
}

// Archetypes and Personalities list the zoo in a fixed order, for drawing.
var (
	Archetypes    = []string{"balanced", "ore-wheat", "wood-brick", "port"}
	Personalities = []string{"fair", "friendly", "wary", "loner"}
)

// jitterSpread is the standard deviation of the log of the factor each
// weight is multiplied by: 0.2 moves most weights by up to about ±20%.
const jitterSpread = 0.2

// ZooBot is one member of the zoo as a game record describes it.
type ZooBot struct {
	Archetype   string      `json:"archetype"`
	Personality string      `json:"personality"`
	Seed        uint64      `json:"seed"`
	Weights     weights     `json:"weights"`
	Trading     personality `json:"trading"`
}

// ParseZoo reads a zoo level. It says false for anything else, including a
// zoo level with an unknown archetype or personality.
func ParseZoo(level string) (ZooBot, bool) {
	parts := strings.Split(level, ":")
	if len(parts) < 3 || len(parts) > 4 || parts[0] != "zoo" {
		return ZooBot{}, false
	}
	base, ok := archetypes[parts[1]]
	trading, known := personalities[parts[2]]
	if !ok || !known {
		return ZooBot{}, false
	}
	z := ZooBot{Archetype: parts[1], Personality: parts[2], Trading: trading}
	if len(parts) == 4 {
		seed, err := strconv.ParseUint(parts[3], 10, 64)
		if err != nil {
			return ZooBot{}, false
		}
		z.Seed = seed
	}
	z.Weights = jitter(base, z.Seed)
	return z, true
}

// ZooLevel writes the level of a zoo bot.
func ZooLevel(archetype, personality string, seed uint64) string {
	return "zoo:" + archetype + ":" + personality + ":" + strconv.FormatUint(seed, 10)
}

// jitter multiplies every weight by its own random factor around 1, drawn
// from the seed in a fixed order, so the same seed gives the same bot.
// Seed 0 leaves the weights as they are.
func jitter(base weights, seed uint64) weights {
	w := base
	w.Resource = map[string]float64{}
	for _, resource := range resources {
		w.Resource[resource] = base.Resource[resource]
	}
	if seed == 0 {
		return w
	}
	rng := rand.New(rand.NewPCG(seed, 0x200))
	shake := func(value float64) float64 { return value * math.Exp(jitterSpread*rng.NormFloat64()) }
	for _, resource := range resources {
		w.Resource[resource] = shake(w.Resource[resource])
	}
	w.Variety = shake(w.Variety)
	w.Port = shake(w.Port)
	w.City = shake(w.City)
	w.Settlement = shake(w.Settlement)
	w.DevCard = shake(w.DevCard)
	return w
}

// zooStyle is the hard level playing with a zoo bot's weights.
func zooStyle(z ZooBot) style {
	look := styles["hard"]
	look.weights = z.Weights
	look.personality = z.Trading
	return look
}
