package main

import (
	"fmt"
	"io"
	"math"
	"strings"
	"time"
)

const maxErrors = 10

// result is how one game went. Winner is -1 when the game gave no result.
type result struct {
	Game     int           `json:"game"`
	RoomID   string        `json:"room_id"`
	Levels   []string      `json:"levels"`
	Winner   int           `json:"winner_seat"`
	Points   []int         `json:"points,omitempty"`
	Turns    int           `json:"turns"`
	Duration time.Duration `json:"duration_ns"`
	Refused  int           `json:"refused"`
	Error    string        `json:"error,omitempty"`
}

// seatLevels rotates the levels by one seat per game, so no level always
// plays first.
func seatLevels(levels []string, game int) []string {
	seats := make([]string, len(levels))
	for seat := range seats {
		seats[seat] = levels[(seat+game)%len(levels)]
	}
	return seats
}

// wilson is the 95% Wilson score interval of wins out of games.
func wilson(wins, games int) (low, high float64) {
	if games == 0 {
		return 0, 1
	}
	const z = 1.96
	n := float64(games)
	p := float64(wins) / n
	center := (p + z*z/(2*n)) / (1 + z*z/n)
	half := z * math.Sqrt(p*(1-p)/n+z*z/(4*n*n)) / (1 + z*z/n)
	return max(0, center-half), min(1, center+half)
}

type rate struct {
	Wins int     `json:"wins"`
	Rate float64 `json:"rate"`
	Low  float64 `json:"ci_low"`
	High float64 `json:"ci_high"`
}

func newRate(wins, games int) rate {
	r := rate{Wins: wins}
	if games > 0 {
		r.Rate = float64(wins) / float64(games)
	}
	r.Low, r.High = wilson(wins, games)
	return r
}

type levelStats struct {
	Level string `json:"level"`
	// Seats is how many seats of a game play this level
	Seats int `json:"seats"`
	// Fair is the share of wins the level would get if every seat played alike
	Fair float64 `json:"fair_share"`
	rate
}

type summary struct {
	Levels      []string      `json:"levels"`
	Games       int           `json:"games"`
	Finished    int           `json:"finished"`
	TimedOut    int           `json:"timed_out"`
	Failed      int           `json:"failed"`
	ByLevel     []levelStats  `json:"by_level"`
	BySeat      []rate        `json:"by_seat"`
	MeanTurns   float64       `json:"mean_turns"`
	MeanTime    time.Duration `json:"mean_duration_ns"`
	MaxTime     time.Duration `json:"max_duration_ns"`
	MeanRefused float64       `json:"mean_refused"`
	Wall        time.Duration `json:"wall_ns"`
	Errors      []string      `json:"errors,omitempty"`
}

// summarize counts only finished games in the win rates; the rest are listed
// as timeouts or failures.
func summarize(levels []string, results []result, wall time.Duration) summary {
	s := summary{Levels: levels, Games: len(results), Wall: wall}
	seatWins := make([]int, len(levels))
	levelWins := map[string]int{}
	turns, refused := 0, 0
	var total time.Duration

	for _, r := range results {
		switch {
		case r.Winner >= 0:
			s.Finished++
			seatWins[r.Winner]++
			levelWins[r.Levels[r.Winner]]++
			turns += r.Turns
			refused += r.Refused
			total += r.Duration
			s.MaxTime = max(s.MaxTime, r.Duration)
		case r.Error == errTimeout:
			s.TimedOut++
		default:
			s.Failed++
			s.Errors = append(s.Errors, fmt.Sprintf("game %d: %s", r.Game, r.Error))
		}
	}

	seen := map[string]bool{}
	for _, level := range levels {
		if seen[level] {
			continue
		}
		seen[level] = true
		seats := 0
		for _, other := range levels {
			if other == level {
				seats++
			}
		}
		s.ByLevel = append(s.ByLevel, levelStats{
			Level: level, Seats: seats, Fair: float64(seats) / float64(len(levels)),
			rate: newRate(levelWins[level], s.Finished),
		})
	}
	for _, wins := range seatWins {
		s.BySeat = append(s.BySeat, newRate(wins, s.Finished))
	}
	if s.Finished > 0 {
		s.MeanTurns = float64(turns) / float64(s.Finished)
		s.MeanTime = total / time.Duration(s.Finished)
		s.MeanRefused = float64(refused) / float64(s.Finished)
	}
	return s
}

func percent(f float64) string { return fmt.Sprintf("%.1f%%", 100*f) }

func (s summary) print(w io.Writer) {
	fmt.Fprintf(w, "levels %s, rotating one seat per game\n", strings.Join(s.Levels, ","))
	fmt.Fprintf(w, "games %d: finished %d, timed out %d, failed %d\n\n", s.Games, s.Finished, s.TimedOut, s.Failed)

	fmt.Fprintf(w, "%-8s %5s %5s %7s  %-15s %s\n", "level", "seats", "wins", "win", "95% CI", "fair share")
	for _, l := range s.ByLevel {
		fmt.Fprintf(w, "%-8s %5d %5d %7s  %-15s %s\n", l.Level, l.Seats, l.Wins, percent(l.Rate),
			percent(l.Low)+"–"+percent(l.High), percent(l.Fair))
	}

	fmt.Fprintf(w, "\n%-8s %5s %7s  %s\n", "seat", "wins", "win", "95% CI")
	for seat, r := range s.BySeat {
		fmt.Fprintf(w, "%-8d %5d %7s  %s\n", seat, r.Wins, percent(r.Rate), percent(r.Low)+"–"+percent(r.High))
	}

	fmt.Fprintf(w, "\nper finished game: %.1f turns, %s on average, %s at most, %.1f refused moves\n",
		s.MeanTurns, s.MeanTime.Round(time.Millisecond), s.MaxTime.Round(time.Millisecond), s.MeanRefused)
	perGame := time.Duration(0)
	if s.Games > 0 {
		perGame = s.Wall / time.Duration(s.Games)
	}
	fmt.Fprintf(w, "wall time %s, %s per game with games in parallel\n", s.Wall.Round(time.Millisecond), perGame.Round(time.Millisecond))
	for i, e := range s.Errors {
		if i == maxErrors {
			fmt.Fprintf(w, "and %d more errors\n", len(s.Errors)-maxErrors)
			break
		}
		fmt.Fprintln(w, e)
	}
}
