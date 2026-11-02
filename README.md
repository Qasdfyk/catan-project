# Catan

Catan for 2–4 players in the browser, with friends over an invite link or against bots.
The full base game: setup, dice, building, the robber, development cards, bank, port and
player trade, Longest Road, Largest Army and a win at 10 points, plus chat.

Shortcuts in the game: `R` rolls, `E` ends the turn, `Esc` leaves build mode.

## Running

With Docker:

```bash
docker compose up --build
```

The game is at <http://localhost:3000>. Create a room and open the invite link in another
tab or browser. Set `INTERNAL_API_KEY` in the environment outside of local play.

Without Docker you need Python 3.12, Go, Node and a Redis server on `localhost:6379`:

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000 --workers 2
```

```bash
cd gateway && go run ./cmd/gateway
```

```bash
cd gateway && go run ./cmd/bots
```

```bash
cd frontend && npm ci && npm run dev
```

The game is then at <http://localhost:5173>.

## Architecture

```
browser ── /api ──▶ FastAPI (rules, rooms) ──▶ Redis (state, lock, pub/sub)
   └────── /ws ───▶ Go gateway (connections) ◀── room events ──┘
                       ▲ └── actions over HTTP ──▶ FastAPI
    Go bots ── /ws ────┘
```

- **backend/** (Python) decides everything. Each change runs load, validate, save and
  publish under a per-room Redis lock, so any number of workers can serve a room.
- **gateway/** (Go) holds the WebSocket connections and room membership. It forwards actions
  and fans out events, giving each seat only its own private state. It knows no game rules.
- **gateway/cmd/bots** (Go) runs one goroutine per bot. A bot is an ordinary client that picks
  from the moves the server calls legal, so it repeats no rule. Run one instance: seats are
  kept in Redis and resumed after a restart.
- **frontend/** (React, TypeScript, SVG) renders the state and the legal moves it receives.

Each seat has a secret token, kept in `sessionStorage`, so every tab is a separate player.
The token is checked on every action. Other players only ever see seat numbers and card
counts. A player whose seat is not connected can return by entering the same name.

The gateway also handles what needs no rules: chat with history, a limit of 10 messages per
second per connection, and counters at `/metrics` in the Prometheus format.

### Why Go is the gateway and the bots

The rules are not a bottleneck: one action costs about 3 ms in Python, and a turn-based game
produces little traffic per room. Fan-out over many connections is what a single Python
thread cannot keep up with, so that is the part in Go. A few players will not notice any
difference; it matters at thousands of connections.

One process, 7.7 kB message to a room of 4, same load generator:

| Load | python-socketio | Go hub |
| --- | --- | --- |
| 400 connections, 100 msg/s | p50 1.1 ms, p99 2.1 ms | p50 0.7 ms, p99 1.5 ms |
| 4,000 connections, 250 msg/s | p50 1.2 ms, p99 2.6 ms, 13.3 s CPU | p50 0.7 ms, p99 1.5 ms, 5.1 s CPU |
| 4,000 connections, 1,000 msg/s | p50 766 ms, p99 4.2 s, 10% undelivered in the window | p50 0.5 ms, p99 3.5 ms, all delivered |
| 10,000 connections, 625 msg/s | p50 1.4 ms, p99 1.8 s, 36 s CPU | p50 0.4 ms, p99 0.9 ms, 7.5 s CPU |

Bots fit Go for the same reason: they are many idle connections. 600 of them, waiting for
their turn, took about 28 MB of memory in one process.

The finished stack delivers an action to both players in 4.5 ms (p50). `gateway/cmd/loadtest`
repeats the gateway side of this measurement against a running stack.

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

```bash
cd gateway && go test ./...
```

```bash
cd frontend && npm test && npm run lint && npm run build
```

Backend integration tests need Redis on `localhost:6379`. `tests/simulation` plays whole
random games through serialization and checks the rules after every action.

`e2e/play.mjs` plays a full game in real browser tabs against a running stack, by clicking
the UI, and checks the lobby, errors and returning by name on the way:

```bash
cd e2e && npm ci && npx playwright install chromium
```

```bash
BASE_URL=http://localhost:5173 PLAYERS=2 BOTS=0 npm test
```

`BOTS` adds bots to the room, and `PLAYERS` sets the number of tabs. A game takes several
minutes, because the tabs play by clicking, with a simple strategy.
