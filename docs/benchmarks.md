# Benchmarks

Everything here comes from `benchmarks/run.sh`, and the raw output is in
[`benchmarks/results/`](../benchmarks/results). All processes, the load generators included,
shared one WSL2 machine with 16 threads and 16 GB of memory, so these numbers show ratios and
limits on this machine, not production capacity.

For scale: a room of 4 players doing one action every 5 seconds produces 0.2 actions per
second and 0.8 messages per second.

## Fan-out: Go gateway and python-socketio

`gateway/cmd/loadtest` adds 7.7 kB room events to Redis and times their delivery to
rooms of 4. `benchmarks/socketio_baseline.py` does the same job with python-socketio in one
process, and sends each client its own message, as the gateway does.

| Connections | Messages/s | python-socketio | Go gateway |
| --- | --- | --- | --- |
| 400 | 400 | p50 1.3 ms, p99 2.5 ms | p50 0.9 ms, p99 1.7 ms |
| 4,000 | 1,000 | p50 1.3 ms, p99 2.5 ms | p50 0.8 ms, p99 1.8 ms |
| 4,000 | 4,000 | p50 1.0 ms, p99 24.4 ms | p50 0.6 ms, p99 1.3 ms |
| 10,000 | 2,500 | p50 1.1 ms, p99 7.0 ms | p50 0.7 ms, p99 1.3 ms |
| 4,000 | 16,000 requested | 8% delivered in the window, p50 1,022 ms | all delivered at about 11,800/s, p50 0.7 ms, p99 2.5 ms |

What this shows, and what it does not:

- **At the size of a real game there is no meaningful difference.** python-socketio is fine
  for this project until thousands of connections.
- The clear result is the limit: python-socketio falls behind somewhere between 4,000 and
  16,000 messages per second, while the gateway delivered everything the generator could send.
- Below that limit the gateway has a steadier tail. The p99 of python-socketio moves a lot
  between runs: 24 and 7 ms here, 54 and 104 ms for the same two rows in an earlier run. The
  p99 of the gateway stayed at 1.3–1.4 ms.
- Memory and CPU are **not** better in these runs (240–590 MB for both). The gateway's numbers
  include real sessions, with two backend calls per connection, while the baseline has no
  authentication. The comparison is not fine enough to claim a difference either way.
- The other reason for the gateway is design, not speed: it lets backend workers scale
  without sticky sessions, as the next section shows.

## Whole stack: throughput against backend workers

`benchmarks/throughput.py` plays real rooms of 2 through the gateway. One action counts when
every player in the room has received the new state. Each room asks for 5 actions per second.

| Workers | Best measured | At 500 actions/s requested |
| --- | --- | --- |
| 1 | 185 actions/s | saturated, p50 477 ms |
| 2 | 347 actions/s | saturated, p50 265 ms |
| 4 | 493 actions/s, limited by the request rate | p50 14.5 ms, p99 218 ms |
| 8 | 702 actions/s | p50 12.2 ms, p99 235 ms |

Throughput nearly doubles from 1 to 2 workers, and 8 workers reach 3.8 times the throughput of
one. One worker can serve about 900 rooms at one action per 5 seconds.

**Overload is the weak spot.** Asked for more than it can do, the stack slows down instead of
refusing work: with 4 workers, 800 rooms got 341 actions/s, below the 493/s of a lighter load,
and p50 rose to 978 ms. Nothing crashed, no room failed, and at most 111 actions out of about
5,900 were refused.

## Two gateways

Run with the two players of each room connected to different gateways, so each event had to
reach a client through the other instance:

| Rooms | Result |
| --- | --- |
| 200, with 4 workers | 483 actions/s, p50 371 ms, p99 788 ms, no failed rooms, no refused actions |

This confirms that the path works across instances. Latency here is high because the machine
was at its limit with two gateways and four load generators, so it says nothing about the
cost of the second gateway.

## Redis Streams

Room events moved from pub/sub to a Redis stream (see the [design notes](design.md)). The
event-path part of `benchmarks/run.sh` (gateway fan-out, and throughput.py through one
gateway) ran twice on the code before and twice after, alternating, on the machine above on
2026-11-07. Each cell shows both runs.

| Measurement | Pub/sub | Stream |
| --- | --- | --- |
| Fan-out, 400 connections, 400 messages/s | p50 0.6 / 0.6 ms, p99 1.1 / 0.9 ms | p50 0.6 / 0.5 ms, p99 1.3 / 1.0 ms |
| Fan-out, 4,000 connections, 4,000 messages/s | p50 0.4 / 0.4 ms, p99 0.8 / 2.2 ms | p50 0.5 / 0.4 ms, p99 1.0 / 0.8 ms |
| Fan-out, 4,000 connections, 16,000/s requested | 55,801 / 57,557 events, p99 1.3 / 0.9 ms | 52,692 / 57,674 events, p99 1.7 / 1.0 ms |
| 4 workers, 100 rooms | 495 / 495 actions/s, p50 5.3 / 7.3 ms | 496 / 495 actions/s, p50 7.6 / 5.3 ms |
| 4 workers, 400 rooms | 830 / 830 actions/s, p50 440 / 436 ms | 815 / 820 actions/s, p50 448 / 448 ms |
| 8 workers, 400 rooms | 992 / 1,143 actions/s | 1,073 / 1,178 actions/s |

The differences are within the spread between runs, so the stream costs nothing measurable.
A first version that called `XINFO STREAM` after every read to look for trimmed events did
cost a lot: 561 actions/s instead of 830 with 4 workers, and a fan-out p50 of 1.2 ms at the
top rate: one more round trip per batch, and its reply carries the first and last events
in full. Checking only after a full batch removed that.

## Measured once, not part of the script

- 600 idle bots in one process took 28 MB of memory on top of 9 MB at rest.

## Bot tournament

`benchmarks/tournament.sh <name> [flags]` starts its own Redis, backend and gateway and runs
`gateway/cmd/tournament`, which plays whole games between bot levels with no bots service:
it opens each room through the REST API and runs every seat in one process. The levels move
one seat per game, so no level always plays first. The report, with the win rate of each
level and seat and a 95% Wilson interval, goes to `benchmarks/results/tournament_<name>.txt`.
`-record file.jsonl` also appends every decision and result as training data, and
`-records DIR` saves the full [game record](game-record.md) of every finished game.

    benchmarks/tournament.sh easy_vs_medium -games 400 -parallel 64 -levels easy,medium,medium,medium

Bots wait 100 ms before each move, because the gateway takes 10 messages a second per
connection and a faster bot gets refused. A game then takes about 40 seconds, and 64 games at
once finish about one game a second on the machine above.

Baseline from 400 games per line, measured on 2026-11-05:

| Table | Result |
| --- | --- |
| 4 × medium | each seat wins 23.5–26.5%, so the seat order gives no edge |
| easy against 3 × medium | easy wins 10.2% (95% CI 7.6–13.6%), against a fair share of 25% |

Games took 96–99 turns and about 41 seconds each. The full reports are in
`benchmarks/results/tournament_medium_x4.txt` and `tournament_easy_vs_medium.txt`.

### Hard level

Hard plays medium's moves where it has nothing better, and adds five heuristics, each on its
own switch in the `style` struct of `gateway/internal/bot/strategy.go`:

- `planner`: picks a goal for the next turns (city, settlement with the roads to it, or a
  development card) by its value over the turns it takes to collect, saves for it instead of
  spending on anything affordable, trades spare cards with the bank toward it, discards what
  the goal does not need and spends down to the discard limit before ending a turn.
- `spots`: rates corners by pips weighted by how rare each resource is on the board, new
  resources and usable ports, less for what the bot already collects (so the second
  settlement complements the first), and builds roads toward the best free corner up to three
  roads away.
- `leader`: puts the robber on the tile that costs the leaders most, never its own, and
  steals from the leader.
- `offers`: proposes 1:1 trades to players for a card the goal needs (at most two offers a
  turn), waits for every answer, confirms the first player to accept or withdraws the offer
  (after 5 seconds without answers too). It declines offers from the leader or from someone
  two points from winning, and accepts only those that bring its own goal closer.
- `longestRoad`: builds roads that lengthen its longest road when two roads or fewer would
  take the Longest Road.

Knights are played to free its own tile and to take the Largest Army; Monopoly names the
resource the others hold most of, which is what is neither in the bank nor in its hand.

Measured on 2026-11-05, one hard against three medium, switching the heuristics on one after
the other (200 games per line, the last 400):

| Hard plays with | Hard wins | 95% CI |
| --- | --- | --- |
| nothing (a copy of medium) | ≈25% | from 4 × medium |
| `planner` | 39.5% | 33.0–46.4% |
| + `spots` | 50.0% | 43.1–56.9% |
| + `leader` | 48.0% | 41.2–54.9% |
| + `offers` | 77.0% | 70.7–82.3% |
| + `longestRoad` (all, 400 games) | 71.5% | 66.9–75.7% |

Most of the gain comes from saving for a goal, better spots and trading with players. Medium
accepts any offer that is not worse for it in card count while it keeps one card of what it
gives, so 1:1 offers usually go through; that part of the gain is against medium in
particular. The robber and the Longest Road add nothing measurable at this sample size.

| Table | Result |
| --- | --- |
| hard against 3 × medium | hard wins 71.5% (95% CI 66.9–75.7%), 0.9 refused moves per game |
| 4 × hard | each seat wins 22.0–28.5%, no game timed out, 4.2 refused moves per game |

Hard games are shorter (72 turns against 96), but with four hard bots a game takes about
73 seconds, as offers wait for every answer. Most refused moves at a table of hard bots are
answers or withdrawals that arrive just after the offer closed. The full reports are in
`benchmarks/results/tournament_hard_vs_medium.txt` and `tournament_hard_x4.txt`.
