package main

import (
	"math"
	"slices"
	"strings"
	"testing"
	"time"
)

func near(a, b float64) bool { return math.Abs(a-b) < 0.0005 }

func TestWilsonMatchesKnownIntervals(t *testing.T) {
	cases := []struct {
		wins, games int
		low, high   float64
	}{
		{50, 100, 0.4038, 0.5962},
		{0, 10, 0, 0.2775},
		{10, 10, 0.7225, 1},
		{100, 400, 0.2103, 0.2944},
	}
	for _, c := range cases {
		low, high := wilson(c.wins, c.games)
		if !near(low, c.low) || !near(high, c.high) {
			t.Errorf("wilson(%d, %d) = %.4f–%.4f, want %.4f–%.4f", c.wins, c.games, low, high, c.low, c.high)
		}
	}
	if low, high := wilson(0, 0); low != 0 || high != 1 {
		t.Errorf("no games should tell nothing: %v–%v", low, high)
	}
}

func TestSeatLevelsRotateEveryLevelThroughEverySeat(t *testing.T) {
	levels := []string{"easy", "medium", "medium", "hard"}
	if got := seatLevels(levels, 0); !slices.Equal(got, levels) {
		t.Fatalf("first game should keep the order: %v", got)
	}
	if got := seatLevels(levels, 1); !slices.Equal(got, []string{"medium", "medium", "hard", "easy"}) {
		t.Fatalf("unexpected rotation: %v", got)
	}

	firstSeat := map[string]int{}
	for game := range 8 {
		firstSeat[seatLevels(levels, game)[0]]++
	}
	if firstSeat["easy"] != 2 || firstSeat["medium"] != 4 || firstSeat["hard"] != 2 {
		t.Fatalf("seat 0 is not shared fairly: %v", firstSeat)
	}
}

func TestSummarizeCountsWinsPerLevelAndSeat(t *testing.T) {
	levels := []string{"easy", "medium", "medium"}
	results := []result{
		{Game: 0, Levels: seatLevels(levels, 0), Winner: 1, Turns: 40, Duration: 2 * time.Second, Refused: 2},
		{Game: 1, Levels: seatLevels(levels, 1), Winner: 2, Turns: 60, Duration: 4 * time.Second},
		{Game: 2, Levels: seatLevels(levels, 2), Winner: 1, Turns: 50, Duration: 3 * time.Second, Refused: 1},
		{Game: 3, Levels: seatLevels(levels, 3), Winner: -1, Error: errTimeout},
		{Game: 4, Levels: seatLevels(levels, 4), Winner: -1, Error: "connection refused"},
	}

	s := summarize(levels, results, 10*time.Second)

	if s.Games != 5 || s.Finished != 3 || s.TimedOut != 1 || s.Failed != 1 {
		t.Fatalf("unexpected counts: %+v", s)
	}
	// Game 1 seats medium,medium,easy and game 2 seats medium,easy,medium
	if len(s.ByLevel) != 2 || s.ByLevel[0].Level != "easy" || s.ByLevel[0].Wins != 2 || s.ByLevel[1].Wins != 1 {
		t.Fatalf("unexpected levels: %+v", s.ByLevel)
	}
	if s.ByLevel[1].Seats != 2 || !near(s.ByLevel[1].Fair, 2.0/3) || !near(s.ByLevel[0].Rate, 2.0/3) {
		t.Fatalf("unexpected medium share: %+v", s.ByLevel)
	}
	if s.BySeat[0].Wins != 0 || s.BySeat[1].Wins != 2 || s.BySeat[2].Wins != 1 {
		t.Fatalf("unexpected seats: %+v", s.BySeat)
	}
	if s.MeanTurns != 50 || s.MeanTime != 3*time.Second || s.MaxTime != 4*time.Second || s.MeanRefused != 1 {
		t.Fatalf("unexpected means: %+v", s)
	}

	var out strings.Builder
	s.print(&out)
	if !strings.Contains(out.String(), "game 4: connection refused") {
		t.Fatalf("failure missing from the report:\n%s", out.String())
	}
}

func TestDrawZooGivesEachZooSeatItsOwnRepeatableBot(t *testing.T) {
	levels := []string{"zoo", "hard", "zoo", "zoo"}
	first := drawZoo(levels, 1, 3)
	if !slices.Equal(first, drawZoo(levels, 1, 3)) {
		t.Fatalf("not repeatable: %v", first)
	}
	if first[1] != "hard" || first[0] == first[2] || first[2] == first[3] {
		t.Fatalf("unexpected seats: %v", first)
	}
	if slices.Equal(first, drawZoo(levels, 1, 4)) || slices.Equal(first, drawZoo(levels, 2, 3)) {
		t.Fatalf("another game or seed drew the same bots: %v", first)
	}
	if levels[0] != "zoo" {
		t.Fatal("drawZoo changed its input")
	}

	// Over many games every archetype and personality sits down
	seen := map[string]bool{}
	for game := range 200 {
		for _, level := range drawZoo([]string{"zoo"}, 1, game) {
			seen[withoutSeed(level)] = true
		}
	}
	if len(seen) != 16 {
		t.Fatalf("drew %d of the 16 kinds of zoo bot", len(seen))
	}
}

func TestSummarizeGroupsZooBots(t *testing.T) {
	levels := []string{"zoo", "hard"}
	results := []result{
		{Levels: []string{"zoo:port:wary:5", "hard"}, Winner: 0},
		{Levels: []string{"hard", "zoo:port:fair:6"}, Winner: 1},
		{Levels: []string{"zoo:ore-wheat:fair:7", "hard"}, Winner: 1},
		{Levels: []string{"zoo:port:wary:8", "hard"}, Winner: -1, Error: errTimeout},
	}

	s := summarize(levels, results, time.Second)

	byName := func(groups []levelStats) map[string]levelStats {
		named := map[string]levelStats{}
		for _, g := range groups {
			named[g.Level] = g
		}
		return named
	}
	level, archetype, trading := byName(s.ByLevel), byName(s.ByArchetype), byName(s.ByPersonality)
	if len(level) != 4 || level["hard"].Wins != 1 || level["hard"].Seats != 1 || level["zoo:port:wary"].Wins != 1 {
		t.Fatalf("unexpected levels: %+v", s.ByLevel)
	}
	if len(archetype) != 2 || archetype["port"].Wins != 2 || !near(archetype["port"].Fair, 2.0/6) {
		t.Fatalf("unexpected archetypes: %+v", s.ByArchetype)
	}
	if len(trading) != 2 || trading["fair"].Wins != 1 || trading["wary"].Wins != 1 {
		t.Fatalf("unexpected personalities: %+v", s.ByPersonality)
	}

	var out strings.Builder
	s.print(&out)
	if !strings.Contains(out.String(), "zoo:ore-wheat:fair") || !strings.Contains(out.String(), "archetype") {
		t.Fatalf("zoo missing from the report:\n%s", out.String())
	}
}

func TestSeatNamesFitAndDiffer(t *testing.T) {
	names := map[string]bool{}
	for seat, level := range []string{"hard", "zoo:wood-brick:friendly:9007199254740991", "zoo:wood-brick:friendly:1", "easy"} {
		name := seatName(level, seat)
		if len(name) > 20 || names[name] {
			t.Fatalf("seat %d: name %q too long or taken", seat, name)
		}
		names[name] = true
	}
}
