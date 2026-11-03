package server

import "time"

const (
	rateBurst     = 20
	ratePerSecond = 10
)

// rateLimiter is a token bucket. It is used by one connection's read loop only,
// so it needs no lock. A game needs far fewer messages than this allows.
type rateLimiter struct {
	now    func() time.Time
	tokens float64
	last   time.Time
}

func newRateLimiter(now func() time.Time) *rateLimiter {
	return &rateLimiter{now: now, tokens: rateBurst, last: now()}
}

func (l *rateLimiter) allow() bool {
	current := l.now()
	l.tokens += current.Sub(l.last).Seconds() * ratePerSecond
	if l.tokens > rateBurst {
		l.tokens = rateBurst
	}
	l.last = current

	if l.tokens < 1 {
		return false
	}
	l.tokens--
	return true
}
