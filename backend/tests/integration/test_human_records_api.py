"""
Games shared for research: each person answers in the lobby, and a finished
game lands in the dataset only as an anonymous copy, only when every person
agreed.
"""
import gzip
import json

import pytest

from app.main import app
from app.services.game_record import fingerprint, replay
from rooms_api import act, clear_bots, create_room, edit_game, join, play_to_the_end, session
from test_rematch import about_to_win


def shared_games():
    directory = app.state.rooms.human_records.directory
    files = sorted(directory.glob("*.json.gz")) if directory.exists() else []
    return [json.loads(gzip.decompress(path.read_bytes())) for path in files]


async def share(client, player, answer=True):
    return await act(client, player["room_id"], player["token"], "share_for_research", {"share": answer})


async def lobby(client, guests=("Bob",)):
    host = await create_room(client)
    return host, [(await join(client, host["room_id"], name)).json() for name in guests]


async def start_and_finish(client, host):
    assert (await act(client, host["room_id"], host["token"], "start_game")).status_code == 200
    await edit_game(host["room_id"], about_to_win)
    assert (await act(client, host["room_id"], host["token"], "end_turn")).status_code == 200


@pytest.mark.asyncio
async def test_lobby_shows_who_agreed(client):
    host, (bob,) = await lobby(client)
    await share(client, bob)

    players = (await session(client, host["room_id"], host["token"]))["public"]["players"]

    assert [p["shares_game"] for p in players] == [False, True]


@pytest.mark.asyncio
async def test_a_player_can_change_their_mind_in_the_lobby(client):
    host, (bob,) = await lobby(client)
    await share(client, host)
    await share(client, bob)
    await share(client, bob, False)

    await start_and_finish(client, host)

    assert shared_games() == []


@pytest.mark.asyncio
async def test_game_everyone_agreed_to_is_shared_anonymously(client):
    host, (bob,) = await lobby(client)
    await share(client, host)
    await share(client, bob)
    await act(client, host["room_id"], host["token"], "start_game")

    stored = await play_to_the_end(client, host["room_id"], [host["token"], bob["token"]])

    (shared,) = shared_games()
    assert [p["name"] for p in shared["players"]] == ["Player 1", "Player 2"]
    text = json.dumps(shared)
    for secret in ("Alice", "Bob", host["room_id"]):
        assert secret not in text
    # Nothing the analysis engine needs is lost: it replays to the same game under the new names
    for player, anonymous in zip(stored.players, shared["players"], strict=True):
        player.name = anonymous["name"]
    assert fingerprint(replay(shared)) == fingerprint(stored)


@pytest.mark.asyncio
async def test_one_person_who_did_not_answer_keeps_the_game_out(client):
    host, (bob, _) = await lobby(client, guests=("Bob", "Carol"))
    await share(client, host)
    await share(client, bob)

    await start_and_finish(client, host)

    assert shared_games() == []
    # The platform record is saved as before
    assert app.state.rooms.records.path(host["room_id"]).exists()


@pytest.mark.asyncio
async def test_bots_need_no_answer(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    await share(client, host)

    await start_and_finish(client, host)
    await clear_bots()

    (shared,) = shared_games()
    assert [(p["name"], p["kind"]) for p in shared["players"]] == [("Player 1", "human"), ("Bot 2", "bot")]


@pytest.mark.asyncio
async def test_a_bot_taking_over_does_not_answer_for_the_player_who_left(client):
    host, (bob,) = await lobby(client)
    await share(client, host)
    await act(client, host["room_id"], host["token"], "start_game")

    await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": bob["seat"]})
    await edit_game(host["room_id"], about_to_win)
    await act(client, host["room_id"], host["token"], "end_turn")
    await clear_bots()

    assert shared_games() == []


@pytest.mark.asyncio
async def test_the_answer_is_fixed_once_the_game_starts(client):
    host, (bob,) = await lobby(client)
    await act(client, host["room_id"], host["token"], "start_game")

    response = await share(client, bob)

    assert response.status_code == 400
    assert response.json()["detail"] == "The game has already started."


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [None, "yes", 1])
async def test_the_answer_is_yes_or_no(client, answer):
    host, _ = await lobby(client)

    response = await share(client, host, answer)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_rematch_asks_again(client):
    host, (bob,) = await lobby(client)
    await share(client, host)
    await share(client, bob)
    await start_and_finish(client, host)
    await act(client, host["room_id"], host["token"], "rematch")

    new_id = (await app.state.redis.get_room(host["room_id"]))["rematch_room_id"]
    new_host = (await client.post(f"/api/rooms/{host['room_id']}/rematch", json={"token": host["token"]})).json()
    players = (await session(client, new_id, new_host["token"]))["public"]["players"]

    assert len(shared_games()) == 1
    assert [p["shares_game"] for p in players] == [False, False]


@pytest.mark.asyncio
async def test_a_failed_shared_copy_does_not_stop_the_game(client, tmp_path):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    await share(client, host)
    # A file where the directory should be makes every save fail
    blocker = tmp_path / "blocked"
    blocker.write_text("")
    app.state.rooms.human_records.directory = blocker

    await start_and_finish(client, host)

    await clear_bots()
    room = await app.state.redis.get_room(host["room_id"])
    assert (room["status"], room["record_saved"]) == ("finished", True)
