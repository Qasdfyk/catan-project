# Human games dataset

The analysis engine is tested on bot games, which are easy to make by the
thousand. Bots are not people, though: they never misread the board, hold a
grudge or forget a card. To know how well the review works for the people it
is meant for, it has to be measured on human games too. This dataset holds them.

It is a **measurement set only**. The games are never used to train a model,
never sold or handed to anyone, and never published one by one. Only numbers
computed over many games are published.

## When a game joins it

Each person decides for themselves, in the lobby, with the box
*Share this game for research* (off by default). The server stores the answer
on the seat (`share_for_research`, action `share_for_research {share: bool}`)
and the lobby shows everyone who agreed.

A finished game is copied into the dataset when
[`eligible(room)`](../backend/app/services/human_records.py) holds:

| Rule | Why |
|---|---|
| At least one person played. | A game of bots only is not a human game. |
| Every person answered yes. Not answering counts as no. | Consent is given, not assumed. |
| A seat a bot took over from a player who left still needs that player's yes. | The bot finished their turns; it cannot agree for them. |
| Bots need no answer. | They are ours. |
| The answer can change only in the lobby. | One answer covers the whole game. |
| A rematch asks again. | Each game is a new decision. |

## What the copy holds

[`anonymize()`](../backend/app/services/human_records.py) takes the closed
platform record ([game-record.md](game-record.md)) and changes three things:

| Field | Platform record | Dataset copy |
|---|---|---|
| `players[].name` | as typed in the lobby | `Player 1`, `Bot 2`… by seat |
| `game_id` and file name | room ID, part of the invite link | 16 random hex digits |
| `started_at`, `finished_at` | UTC, to the second | the date only |

Everything else stays, so a copy replays to the same game as the original
(the integration tests check this with `fingerprint`). The record format holds
no chat and no tokens, so nothing else names a person.

The copy is anonymous for whoever reads the dataset. It is not anonymous for
the operator of the server, who also holds the platform records: the two files
share their board and moves. The dataset is kept apart so it can be handed to
the engine on its own.

## Where it lives

`HUMAN_RECORDS_DIR` (default `records-human`, `/data/records-human` in Docker),
one `<random id>.json.gz` per game, written by the same atomic `RecordStore` as
the platform records. The copy is written once, right after the platform
record is saved; if that write fails the game is lost from the dataset and
nothing else happens, which is logged.

## Changing the rules

The terms page (`frontend/src/pages/Terms.tsx`, at `/terms`) tells players the
same thing as this file. Change the code, this file and the page together.
