# Design notes

The decisions that shaped the system, what they cost, and what is still missing.

## One authority, and clients that only ask

All game state and every rule live in the Python backend. The browser, the gateway and
the bots never decide anything: they send an intent, and the backend answers with a new state
or a refusal. The server also computes the legal moves for each seat, so the board highlights
and the bots read the same list, and the UI cannot drift from the rules.

## The path of an action

1. The browser sends `{action, payload}` to the gateway over a WebSocket.
2. The gateway forwards it over HTTP with the seat's token.
3. The backend takes the room's Redis lock, loads the state, checks the token, applies the
   action and saves the result.
4. Still under the lock, it publishes one event to Redis: the public state plus a private
   part for each seat.
5. Every gateway subscribed to the channel sends each of its clients the public state and
   only that client's private part.

Publishing under the lock gives each room a total order of events. A `version` number covers
the one race that is left, when a client reconnects and an event overtakes its snapshot.

## Why state is reloaded for every action

The backend keeps nothing in memory between requests. An action costs a Redis round trip and
a deserialization, which puts one worker at about 185 actions per second, but any worker can serve any room, a crash loses nothing, and
workers can be added without sticky sessions. For a turn-based game that is a good trade.

## Sessions

A seat is identified by a secret token, checked on every action, so taking a seat over ends
the old session at once. Other players only see seat numbers. A token lives in
`sessionStorage`, which keeps each tab a separate player and makes local testing easy.

Returning to a game needs only the name, so there are no accounts, but anyone who knows the
room link and a name could take a seat that is not connected. That is acceptable between
friends, and not for a public service.

## Seats do not move

The gateway remembers a connection's seat and routes private state by it, so a seat number
must never change. Bots can therefore only be removed from the last seat. The alternative was
to have the gateway track seat changes, which is more code to protect a rare lobby action.

## Bots are ordinary clients

A bot connects to the gateway like a browser and picks from the moves the server lists as
legal. It has its own heuristics, but no rule is written twice, and a bot cannot cheat because
it only sees its own view. If the server refuses a move, a fallback does only what cannot fail,
which keeps a bug in the strategy from stopping a game.

Active seats are stored in a Redis set, so the service resumes its games after a restart. It
is meant to run as a single instance: two would play the same seats.

## Failure behaviour

| Failure | What happens |
| --- | --- |
| A tab closes | The seat shows as offline. The player returns by name, or anyone hands the seat to a bot |
| The gateway restarts | Clients reconnect with backoff and resync from a snapshot |
| A client cannot keep up | Its connection is dropped, so it cannot block others, and it resyncs on reconnect |
| The bot service restarts | Bots resume their seats from Redis |
| A gateway crashes | Presence keys expire within 45 s, which frees its seats |
| The room lock times out | The action is refused with 503, and nothing changes |

## Known limits

- Redis is a single point of failure, and pub/sub delivers at most once. A gateway that loses
  its subscription misses events until its clients next receive a state.
- There is no turn timer. An offline player is replaced only when someone asks for it.
- Bots play by heuristics and do not make trade offers of their own.
- REST endpoints have no rate limit, and there are no accounts.
- Above its capacity the backend gets slower instead of shedding load: see
  [benchmarks](benchmarks.md).
- Rules are checked by tests and by random games, not against a reference implementation.
