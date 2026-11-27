"""
The human games dataset: anonymous copies of finished games in which every
person at the table agreed to share the game for research. It is kept apart
from the platform records and is used only to measure the analysis engine on
human play, never to train it. docs/human-records.md describes the rules and
the terms page in the frontend says the same to players.

    if eligible(room):
        dataset_id = new_dataset_id()
        store.save(dataset_id, anonymize(record, dataset_id))
"""
import copy
import secrets
from typing import Any, Dict


def is_person(entry: Dict[str, Any]) -> bool:
    """
    Whether a person sat in this seat. A seat a bot took over from a player who
    left is still theirs: the bot only finished some of their turns.
    """
    return not entry.get("bot") or entry.get("replaced", False)


def eligible(room: Dict[str, Any]) -> bool:
    """
    A game joins the dataset when at least one person played and every person
    agreed. One refusal, or one person who never answered, keeps it out.
    Games of bots only are not human games.
    """
    people = [entry for entry in room["seats"] if is_person(entry)]
    return bool(people) and all(entry.get("share_for_research") is True for entry in people)


def new_dataset_id() -> str:
    """Random, so nothing in the dataset leads back to the room or its link."""
    return secrets.token_hex(8)


def anonymize(record: Dict[str, Any], dataset_id: str) -> Dict[str, Any]:
    """
    A copy of a closed platform record that holds no names, no room ID and no
    time of day. Everything the analysis engine needs stays: the board, the
    deck, every event and which seats were bots.
    """
    if record.get("finished_at") is None:
        raise ValueError("Only finished games go into the dataset.")
    anonymous = copy.deepcopy(record)
    anonymous["game_id"] = dataset_id
    # The date is enough to tell old games from new ones; the hour could tell who played
    anonymous["started_at"] = record["started_at"][:10]
    anonymous["finished_at"] = record["finished_at"][:10]
    for player in anonymous["players"]:
        role = "Bot" if player["kind"] == "bot" else "Player"
        player["name"] = f"{role} {player['seat'] + 1}"
    return anonymous
