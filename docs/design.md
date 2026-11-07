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

The backend asks for a bot by adding an entry to the Redis stream `catan:bots`, which the bot
service reads as the consumer group `bots`. An entry stays pending while its bot plays and is
acknowledged only when the seat is over, so a summon is kept while the service is down and
any number of instances can share the seats. Each instance refreshes its pending entries every
30 s, and claims entries idle for 2 minutes, which are those of an instance that stopped. A
bot whose entry another instance claimed stops, so a seat has one bot. The group starts at the
beginning of the stream, so seats summoned before the service first ran are played too.

An instance is named by `BOTS_CONSUMER` or its host name, and resumes the seats pending under
its name at once on start. If another live instance holds the name, a random suffix is added.
Every instance also runs the turn timer, which is safe because the backend ends a turn only
once its deadline has passed.

## Failure behaviour

| Failure | What happens |
| --- | --- |
| A tab closes | The seat shows as offline. The player returns by name, or anyone hands the seat to a bot |
| The gateway restarts | Clients reconnect with backoff and resync from a snapshot |
| A client cannot keep up | Its connection is dropped, so it cannot block others, and it resyncs on reconnect |
| The bot service restarts | Bots resume their seats at once after a clean stop, within about 2 minutes after a crash |
| One of several bot instances dies | The others take its seats over within about 2 minutes |
| A gateway crashes | Presence keys expire within 45 s, which frees its seats |
| The room lock times out | The action is refused with 503, and nothing changes |

## Known limits

- Redis is a single point of failure, and pub/sub delivers at most once. A gateway that loses
  its subscription misses events until its clients next receive a state.
- An offline player is replaced only when someone asks for it. The turn timer, if the room
  has one, only finishes their turns.
- The bot stream is capped at about 10,000 entries. A seat summoned that many summons ago and
  still playing loses its entry, and is not resumed if its instance then dies.
- A bot instance cut off from Redis for over 2 minutes keeps playing its seats until it can
  reach Redis again, while another instance plays them too.
- Bots play by heuristics and do not make trade offers of their own.
- REST endpoints have no rate limit, and there are no accounts.
- Above its capacity the backend gets slower instead of shedding load: see
  [benchmarks](benchmarks.md).
- Rules are checked by tests and by random games, not against a reference implementation.
