# Game record format

A game record is one JSON document that describes a finished game completely: the board, the
players, every accepted action in order, the outcome of every chance, and which players saw
each hidden outcome. It is written by the platform and read by the
[analysis engine](https://github.com/Qasdfyk/catan-analysis-engine), which replays games move
by move and judges each decision only by what the player knew at the time.

The code is in `backend/app/services/game_record.py` (writing, reading, replaying) and
`backend/app/models/recording.py` (capturing actions in the rules engine).

```bash
cd backend
.venv/bin/python -m app.services.game_record simulate --seed 7 --out game.json
.venv/bin/python -m app.services.game_record check game.json
```

## Design

- **A record is complete when it replays.** Replaying feeds every event through the same
  `apply_action` the server uses for live moves, with the recorded outcomes in place of the
  random source. The tests record random games, including turns finished by the timer, and
  check that the replay ends in exactly the same state and records exactly the same events.
- **Events are what the player did, not what changed.** An event holds the action as the
  client sends it, so a reader needs the rules to get the state, and a reader with the rules
  gets every intermediate state for free. Resource payouts, Longest Road and the end of the
  game follow from the rules and are not written down.
- **Only chance is recorded.** The board and the deck order are in the header. Dice and the
  card taken by a steal are in the event that caused them. Everything else is deterministic.
- **Visibility is per outcome.** An outcome without `visible_to` was seen by everyone. Only two
  kinds of outcome are hidden; see [What each player saw](#what-each-player-saw).
- **Positions use the backend's cube coordinates**, so a record does not depend on any
  numbering. Engines map them to their own indices when they load a record.

## Document

```json
{
  "format": "catan-game-record",
  "version": 1,
  "source": "platform",
  "game_id": "AB12CD",
  "started_at": "2026-11-08T19:56:02+00:00",
  "finished_at": "2026-11-08T20:41:17+00:00",
  "settings": {"victory_points": 10, "discard_limit": 7, "desert": "random",
               "friendly_robber": false, "turn_seconds": null},
  "players": [
    {"seat": 0, "name": "Alice", "color": "red", "kind": "human", "bot_level": null},
    {"seat": 1, "name": "Bot 1", "color": "blue", "kind": "bot", "bot_level": "hard"}
  ],
  "board": {
    "tiles": [{"hex": {"q": -2, "r": 0, "s": 2}, "resource": "wheat", "number": 4}],
    "ports": [{"type": "3:1", "vertices": [{"hex": {"q": -3, "r": 0, "s": 3}, "direction": 0},
                                           {"hex": {"q": -3, "r": 0, "s": 3}, "direction": 1}]}],
    "robber": {"q": 0, "r": 0, "s": 0}
  },
  "dev_deck": {"cards": ["knight", "knight", "victory_point"], "visible_to": []},
  "events": [
    {"turn": 0, "seat": 0, "action": "build_settlement",
     "payload": {"hex": {"q": -2, "r": 0, "s": 2}, "direction": 0}},
    {"turn": 8, "seat": 0, "action": "roll_dice", "payload": {}, "outcome": {"dice": [3, 5]}},
    {"turn": 21, "seat": 1, "action": "steal", "payload": {"victim_seat": 0},
     "outcome": {"resource": "ore"}, "visible_to": [0, 1]}
  ],
  "result": {"winner_seat": 0, "victory_points": [10, 7], "turns": 180}
}
```

Lists are shortened above: a standard board has 19 tiles and 9 ports, and the deck has 25 cards.

| Field | Meaning |
|---|---|
| `format`, `version` | Always `"catan-game-record"` and, for this document, `1`. A reader refuses other versions. |
| `source` | `platform` (a game played on the site), `tournament` (bots against each other) or `simulation` (random players, for tests). |
| `game_id` | The room id on the platform, or `null`. |
| `started_at`, `finished_at` | UTC, ISO 8601. `finished_at` and `result` are `null` until the game ends. |
| `settings` | The house rules of the game, as in `GameSettings`. |
| `players` | One entry per seat, in seat order. Colors follow seat order: red, blue, white, orange. `kind` is `human` or `bot`; `bot_level` is `easy`, `medium`, `hard`, `random` or `null`. |
| `board.tiles` | Every land tile: its hex, `resource` (`wood`, `brick`, `sheep`, `wheat`, `ore`, `desert`) and `number` (`null` on the desert). |
| `board.ports` | Every port: `type` (`3:1` or `2:1` with a resource) and the two vertices that use it. |
| `board.robber` | Where the robber starts: the desert. |
| `dev_deck.cards` | The development cards in the order they will be drawn, first card first. `visible_to: []`: nobody knew the order. |
| `events` | Every accepted action, in order. |
| `result` | `winner_seat`, final `victory_points` per seat counting hidden victory point cards, and `turns`, the number of turns ended (setup turns included). |

## Positions

Hexes use cube coordinates `{"q", "r", "s"}` with `q + r + s = 0`; the board is pointy-topped
and the center hex is `(0, 0, 0)`. Hex neighbors are numbered clockwise from east: 0 east,
1 south-east, 2 south-west, 3 west, 4 north-west, 5 north-east.

A vertex or an edge is a hex plus a direction from 0 to 5:

- **Vertex `d`** is the corner between neighbors `d - 1` and `d`. Vertex 0 is the upper right
  corner, and they go clockwise: 1 lower right, 2 bottom, 3 lower left, 4 upper left, 5 top.
- **Edge `d`** is the side shared with neighbor `d`, from vertex `d` to vertex `d + 1`.

A corner belongs to up to three hexes, so it has up to three spellings. Events always use the
**canonical** one: of the equivalent `(hex, direction)` pairs, the one whose hex is smallest
when `(q, r, s)` is compared in order. The hex may lie in the sea. Port vertices in the header
may use any spelling, so readers should canonicalize them on load (`hex_lib.py` has both rules).

## Events

Every event has:

| Field | Meaning |
|---|---|
| `turn` | Turns ended before this action; increases by one with each `end_turn`. The setup's placements fill turns `0` to `2 × players − 1`. |
| `seat` | Who acted. During a discard after a 7 that is the discarding player, not the one whose turn it is. |
| `action`, `payload` | Exactly what the client sends to the gateway (see the table below). |
| `outcome` | Only for actions that involve chance. |
| `visible_to` | Present only when `outcome` was hidden: the seats that saw it, sorted. |
| `auto` | `true` when the turn timer made the move because the player ran out of time. Absent otherwise. |

| `action` | `payload` | `outcome` |
|---|---|---|
| `build_settlement`, `build_road`, `upgrade_city` | a vertex (settlement, city) or an edge (road), as above | |
| `roll_dice` | `{}` | `{"dice": [d1, d2]}` |
| `discard` | `{"cards": {"ore": 1, "brick": 2}}` | |
| `move_robber` | `{"hex": {...}}` | |
| `steal` | `{"victim_seat": 0}` | `{"resource": "ore"}`, hidden |
| `buy_dev_card` | `{}` | `{"card": "knight"}`, hidden |
| `play_knight`, `play_road_building` | `{}` | |
| `play_year_of_plenty` | `{"first": "sheep", "second": "ore"}` | |
| `play_monopoly` | `{"resource": "ore"}` | |
| `trade_with_bank` | `{"give": "ore", "get": "sheep"}` (one card bought at the player's rate) | |
| `offer_trade` | `{"give": {...}, "get": {...}}` | |
| `respond_trade` | `{"accept": true}` | |
| `confirm_trade` | `{"partner_seat": 0}` | |
| `cancel_trade` | `{}` | |
| `end_turn` | `{}` | |

The free roads of Road Building and the placements of the setup are ordinary `build_road` and
`build_settlement` events; the phase of the game says they cost nothing. A refused action
leaves no event.

## What each player saw

The platform shows everyone the board, every action, the dice, each player's card count and
the exact contents of the bank. From the bank alone anyone can work out what was discarded,
what a bank trade or Year of Plenty took, and what each roll paid out, so all of those are
public. Two things are not:

| Hidden outcome | Seen by |
|---|---|
| The card taken by `steal` | The thief and the victim. Everyone else knows only that one card moved. |
| The card drawn by `buy_dev_card` | The buyer. The others learn it when it is played, or at the end of the game for victory point cards. |
| The order of `dev_deck` | Nobody. |

To judge a decision fairly, a reader keeps for each seat only the outcomes that list it (or
have no `visible_to`) and treats the rest as unknown: the analysis engine fills them in by
sampling hands consistent with what that seat saw (determinization).

## Replaying

`replay(record, upto=None)` in `game_record.py` rebuilds the game from the header, then applies
the events one by one. Before each event the game's random source is replaced by the event's
outcome: `roll_dice` takes its two dice from it and `steal` takes its card. With `upto` it stops
after that many events, which gives the state at any point of the game. It raises `RecordError`
at the first event that does not fit, for example dice that are not 1 to 6, a stolen card the
victim did not hold, or an action the rules refuse.

## Compatibility

New optional fields may be added without changing `version`; readers ignore fields they do not
know. Removing or changing the meaning of a field, or changing what a reader must do to replay
a game, raises `version` by one.
