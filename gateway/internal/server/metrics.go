package server

import (
	"fmt"
	"net/http"
	"sync/atomic"
	"time"
)

// Upper bounds, in seconds, of the action latency histogram.
var latencyBuckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1}

// Metrics are counters in the Prometheus text format.
type Metrics struct {
	Connections     atomic.Int64
	Actions         atomic.Int64
	EventsDelivered atomic.Int64
	EventsRead      atomic.Int64
	EventReadErrors atomic.Int64
	Resyncs         atomic.Int64
	RateLimited     atomic.Int64
	ClientsDropped  atomic.Int64

	latencyCounts [8]atomic.Int64
	latencyNanos  atomic.Int64
}

// ObserveAction records how long the backend took to handle an action.
func (m *Metrics) ObserveAction(elapsed time.Duration) {
	m.Actions.Add(1)
	m.latencyNanos.Add(elapsed.Nanoseconds())
	for i, bound := range latencyBuckets {
		if elapsed.Seconds() <= bound {
			m.latencyCounts[i].Add(1)
			return
		}
	}
}

func (m *Metrics) Handler(hub *Hub) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		rooms, clients := hub.Size()
		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintf(w, "catan_gateway_rooms %d\n", rooms)
		fmt.Fprintf(w, "catan_gateway_clients %d\n", clients)
		fmt.Fprintf(w, "catan_gateway_connections_total %d\n", m.Connections.Load())
		fmt.Fprintf(w, "catan_gateway_actions_total %d\n", m.Actions.Load())
		fmt.Fprintf(w, "catan_gateway_events_delivered_total %d\n", m.EventsDelivered.Load())
		fmt.Fprintf(w, "catan_gateway_events_read_total %d\n", m.EventsRead.Load())
		fmt.Fprintf(w, "catan_gateway_event_read_errors_total %d\n", m.EventReadErrors.Load())
		fmt.Fprintf(w, "catan_gateway_resyncs_total %d\n", m.Resyncs.Load())
		fmt.Fprintf(w, "catan_gateway_rate_limited_total %d\n", m.RateLimited.Load())
		fmt.Fprintf(w, "catan_gateway_clients_dropped_total %d\n", m.ClientsDropped.Load())

		cumulative := int64(0)
		for i, bound := range latencyBuckets {
			cumulative += m.latencyCounts[i].Load()
			fmt.Fprintf(w, "catan_gateway_action_seconds_bucket{le=\"%g\"} %d\n", bound, cumulative)
		}
		fmt.Fprintf(w, "catan_gateway_action_seconds_bucket{le=\"+Inf\"} %d\n", m.Actions.Load())
		fmt.Fprintf(w, "catan_gateway_action_seconds_sum %g\n", float64(m.latencyNanos.Load())/1e9)
		fmt.Fprintf(w, "catan_gateway_action_seconds_count %d\n", m.Actions.Load())
	})
}
