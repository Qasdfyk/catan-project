# Bot zoo

The [analysis engine](https://github.com/Qasdfyk/catan-analysis-engine) will judge a move by
playing the rest of the game out many times. The opponents in those games must play the way
different people do: if every simulated opponent played like the hard bot, a move that only
works against the hard bot would look good. Later the same bots train a value network, where
games of one style would teach it one style. So besides its three levels, the platform has a
zoo: the hard bot's judgement turned by weights, in many combinations.

The code is in `gateway/internal/bot/zoo.go`, the statistics in
`backend/app/services/record_stats.py`.

## What a zoo bot is

A zoo bot is the hard level with three things set:

- **An archetype** decides what it builds toward. It scales the value of each resource when
  the bot rates a building spot, the bonus for variety and for ports, the value of each goal
  (city, settlement, development card) and how far behind the Longest Road it still builds
  for it.
- **A personality** decides how it trades with players: how many offers it makes in a turn,
  whether it takes a trade that leaves its goal no closer, and whom it refuses (the embargo).
- **A seed** multiplies every weight of the archetype by its own random factor around 1
  (log-normal, σ = 0.2, so most factors fall between 0.8 and 1.2). The same seed gives the
  same bot; seed 0 shakes nothing.

| Archetype | Plays for | Weights that differ from balanced |
|---|---|---|
| `balanced` | whatever its goal planner finds best, like hard | none |
| `ore-wheat` | cities and development cards | ore 1.4, wheat 1.3, wood and brick 0.75; city 1.3, card 1.6, settlement 0.9; Longest Road only one road behind |
| `wood-brick` | settlements and the Longest Road | wood and brick 1.4, ore 0.7; settlement 1.3, city 0.85, card 0.6; Longest Road up to three roads behind |
| `port` | lots of one resource and the port that sells it | variety 0.3 (a resource it already collects loses little value), ports 3× |

| Personality | Offers a turn | Takes a trade that | Refuses |
|---|---|---|---|
| `fair` | 2 | brings its goal closer | the leader and anyone two points from winning |
| `friendly` | 3 | leaves its goal no further away | nobody |
| `wary` | 1 | brings its goal closer | also anyone ahead of itself, and it will not confirm its own offer with them |
| `loner` | 0 | nothing | everyone |

`zoo:balanced:fair` with no seed is the hard level itself. A test checks that on several
positions, and before the change 5,765 decisions recorded from a tournament of hard and
medium bots were replayed through the new code: every one came out the same.

### Levels

A zoo bot is a level string, `zoo:<archetype>:<personality>[:<seed>]`, for example
`zoo:ore-wheat:friendly:1234`. The bot is stateless: every decision parses the level and
shakes the weights again from the seed, which takes microseconds and means nothing has to be
kept between moves. An unknown archetype or personality plays as medium, like any unknown
level. The lobby does not offer zoo bots; they live in tournaments and in the records.

## Tournaments

```bash
cd gateway
go run ./cmd/tournament -games 400 -levels zoo,zoo,zoo,zoo -records ../records/zoo
```

A seat of level `zoo` draws a new bot every game: archetype, personality and weight seed,
all from `-seed`, the game and the seat, so a rerun seats the same bots. Seeds stay below
2^53, so a JSON number holds them exactly in any reader. A fixed zoo bot such as
`zoo:port:wary` can sit in `-levels` too. The summary adds win rates by archetype and by
personality. A zoo seat is named after its archetype and seat number ("port 2"), since a name
has at most 20 characters and joining under a taken name takes that seat back.

Each record marks the seat `"bot_level": "zoo"` with a `bot_style` holding the archetype,
personality, seed and the weights after shaking ([game-record.md](game-record.md)), so a
record says how its bots played without the bot's code.

## Statistics from records

```bash
cd backend
.venv/bin/python -m app.services.record_stats ../records/zoo
.venv/bin/python -m app.services.record_stats ../records/zoo --json > zoo.json
```

`record_stats` replays every record (in parallel) and works everything out from the record
alone, so it describes any set of games in the format: tournaments, games on the site, and
later games converted from elsewhere. Seats are grouped by archetype for zoo bots and by level
otherwise. It reports:

- per group: win rate, final points, buildings, roads, development cards, trades with players
  and the bank, how often the player ends with a port, and the **opening**: the share of the
  dice that pay its two starting settlements, by resource;
- per personality: wins, offers, trades;
- **head to head**: for every two groups, how often a seat of one finished above a seat of
  the other at the same table (the winner is above everyone, then points; a tie counts half);
- **what the winners held**: where their points came from, and whether they had the Longest
  Road, the Largest Army, both or neither, with the entropy of that mix in bits;
- **spread**: the standard deviation of several seat facts over all seats, to compare how
  varied two sets of games are;
- **eta²** of the same facts: the share of their variance explained by the group. Near 0
  the groups play alike; near 1 the group alone fixes the value.

A test checks the point sources against the record: settlements, twice the cities, victory
point cards and both bonus cards add up to the final points of every seat, which the record
states independently.

## Results

Measured on 2026-11-15: 400 games of `-levels zoo,zoo,zoo,zoo -seed 1 -delay 40ms`, all 400
finished, 74.6 turns on average by the tournament's count (81.6 by the records, which count
setup turns too). Statistics from `record_stats`.

**The archetypes play differently.** Per player at the end of a game:

| Archetype | Seats | Wins per seat | Opening on ore + wheat | On wood + brick | Cities | Settlements | Roads | Dev cards | Ends with a port |
|---|---|---|---|---|---|---|---|---|---|
| ore-wheat | 390 | 30.0% | 53.6% | 25.3% | 2.51 | 0.73 | 4.8 | 5.3 | 50% |
| balanced | 377 | 27.6% | 40.9% | 39.2% | 2.29 | 1.82 | 6.7 | 2.6 | 71% |
| wood-brick | 445 | 23.6% | 27.2% | 55.4% | 1.46 | 3.19 | 8.1 | 1.1 | 76% |
| port | 388 | 19.1% | 38.7% | 38.8% | 2.04 | 1.58 | 5.8 | 2.6 | 93% |

An even share is 25%. Ore-wheat turns its settlements into cities (0.7 settlements left
against 3.2 for wood-brick) and buys five times the development cards; wood-brick builds
almost twice the roads. The port bot ends next to a port 93% of the time and is the weakest:
a 2:1 port is worth less than the variety it gives up.

**Who beats whom** (row finished above column at the same table):

| | ore-wheat | balanced | wood-brick | port |
|---|---|---|---|---|
| ore-wheat | | 58.0% | 57.5% | 64.4% |
| balanced | 42.0% | | 55.9% | 64.3% |
| wood-brick | 42.5% | 44.1% | | 53.8% |
| port | 35.6% | 35.7% | 46.2% | |

The order is transitive: there is no rock-paper-scissors, and ore-wheat is the strongest
archetype among these bots. The spread is wide enough to matter in simulations (36–64%) and narrow enough
that every archetype wins a fair number of games.

**Personalities** (per seat): fair 27.9%, wary 27.9%, loner 22.8%, friendly 21.8%. Friendly
makes twice the trades of fair (10.8 against 5.2 a game) and still wins least, since it also
trades with the leader. Trading counts tell nothing about the archetype (eta² 0.00): it is the
personality that trades.

**Diversity.** The archetype explains 23% of the variance of the ore + wheat opening, 30% of
wood + brick, 27% of settlements left, 22% of roads and 20% of development cards (eta²); the
rest is the board and the dice. Winners held the Longest Road alone in 203 games, the Largest
Army alone in 112, both in 13 and neither in 72: an entropy of 1.62 bits out of 2.

**Against four hard bots.** The same statistics over 200 games of `-levels hard,hard,hard,hard
-seed 1` (all finished, 83.0 turns by the records against 81.6 for the zoo):

| Spread between seats (standard deviation) | 4 × hard | Zoo | Change |
|---|---|---|---|
| Opening on ore + wheat | 0.138 | 0.198 | +43% |
| Opening on wood + brick | 0.134 | 0.200 | +49% |
| Trades with players | 2.13 | 5.27 | +148% |
| Development cards | 2.94 | 3.39 | +15% |
| Roads | 2.30 | 2.67 | +16% |
| Settlements left | 1.62 | 1.74 | +8% |
| Cities | 1.18 | 1.19 | +1% |

Seats differ more in the zoo, most in how they open and how they trade. The way games are
won barely changes: the winners' mix of bonus cards has an entropy of 1.64 bits with four
hard bots and 1.62 with the zoo, and cities give 61% and 56% of the winners' points. That is
worth knowing before the zoo plays opponents in simulations: it varies what players do far
more than how the game ends.

The tournament summaries and reports are in `benchmarks/results/` (`tournament_zoo_x4.json`,
`tournament_hard_x4_seed1.json`, `record_stats_zoo_x4.txt`, `record_stats_hard_x4.txt`). The
records themselves are not in the repository; the tournaments rebuild them from the same seed.
