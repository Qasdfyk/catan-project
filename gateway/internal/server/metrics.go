package server

import (
	"fmt"
	"net/http"
	"sync/atomic"
)

// Metrics are counters in the Prometheus text format.
type Metrics struct {
	Connections     atomic.Int64
	Actions         atomic.Int64
	EventsDelivered atomic.Int64
	RateLimited     atomic.Int64
	ClientsDropped  atomic.Int64
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
		fmt.Fprintf(w, "catan_gateway_rate_limited_total %d\n", m.RateLimited.Load())
		fmt.Fprintf(w, "catan_gateway_clients_dropped_total %d\n", m.ClientsDropped.Load())
	})
}
