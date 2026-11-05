# Benchmarks

Everything here comes from `benchmarks/run.sh`, and the raw output is in
[`benchmarks/results/`](../benchmarks/results). All processes, the load generators included,
shared one WSL2 machine with 16 threads and 16 GB of memory, so these numbers show ratios and
limits on this machine, not production capacity.

For scale: a room of 4 players doing one action every 5 seconds produces 0.2 actions per
second and 0.8 messages per second.

## Fan-out: Go gateway and python-socketio

`gateway/cmd/loadtest` publishes 7.7 kB room events to Redis and times their delivery to
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

## Measured once, not part of the script

- 600 idle bots in one process took 28 MB of memory on top of 9 MB at rest.

## Bot tournament

`benchmarks/tournament.sh <name> [flags]` starts its own Redis, backend and gateway and runs
`gateway/cmd/tournament`, which plays whole games between bot levels with no bots service:
it opens each room through the REST API and runs every seat in one process. The levels move
one seat per game, so no level always plays first. The report, with the win rate of each
level and seat and a 95% Wilson interval, goes to `benchmarks/results/tournament_<name>.txt`.
`-record file.jsonl` also appends every decision and result as training data.

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
