import json

import pytest

from app.main import app
from app.models.game import TurnPhase
from app.models.player import DevCard
from rooms_api import (
    act, clear_bots, create_room, edit_game, join, last_summon, next_event, past_setup, session, started_room,
    stream_tail, summoned_since,
)

CHOSEN = {"victory_points": 8, "discard_limit": 9, "desert": "center", "friendly_robber": True, "turn_seconds": 90}


def about_to_win(game):
    past_setup(game)
    game.turn_phase = TurnPhase.MAIN_PHASE
    game.players[0].dev_cards = [DevCard.VICTORY_POINT] * 9


async def finish(client, host):
    """The host wins by ending the turn with enough hidden points."""
    await edit_game(host["room_id"], about_to_win)
    assert (await act(client, host["room_id"], host["token"], "end_turn")).status_code == 200


async def finished_room(client, guests=("Bob",), bots=0):
    host = await create_room(client)
    sessions = [(await join(client, host["room_id"], name)).json() for name in guests]
    for _ in range(bots):
        await act(client, host["room_id"], host["token"], "add_bot")
    await act(client, host["room_id"], host["token"], "start_game")
    await finish(client, host)
    return host, sessions


async def rematch(client, room_id, token):
    return await client.post(f"/api/rooms/{room_id}/rematch", json={"token": token})


@pytest.mark.asyncio
async def test_rematch_opens_a_lobby_with_the_same_players(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()
    await act(client, host["room_id"], host["token"], "update_settings", CHOSEN)
    await act(client, host["room_id"], host["token"], "start_game")
    await finish(client, host)

    response = await act(client, host["room_id"], host["token"], "rematch")

    assert response.status_code == 200
    old = (await session(client, host["room_id"], guest["token"]))["public"]
    assert old["status"] == "finished"
    new_id = old["rematch_room_id"]
    assert new_id and new_id != host["room_id"]

    joined = (await rematch(client, host["room_id"], guest["token"])).json()
    assert joined["room_id"] == new_id
    assert joined["seat"] == guest["seat"]
    new = (await session(client, new_id, joined["token"]))["public"]
    assert new["status"] == "lobby"
    assert new["host_seat"] == 0
    assert new["settings"] == CHOSEN
    assert new["rematch_room_id"] is None
    assert new["turn_deadline"] is None
    assert [p["name"] for p in new["players"]] == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_everyone_hears_of_the_rematch(client):
    host, _ = await finished_room(client)
    after = await stream_tail()

    await act(client, host["room_id"], host["token"], "rematch")

    event = json.loads(await next_event(host["room_id"], after))
    assert event["room_id"] == host["room_id"]
    assert event["public"]["rematch_room_id"] is not None


@pytest.mark.asyncio
async def test_rematch_tokens_lead_to_the_same_seats(client):
    host, (bob, charlie) = await finished_room(client, guests=("Bob", "Charlie"))
    await act(client, host["room_id"], host["token"], "rematch")

    sessions = [(await rematch(client, host["room_id"], s["token"])).json() for s in (host, bob, charlie)]

    assert [s["seat"] for s in sessions] == [0, 1, 2]
    assert len({s["token"] for s in sessions}) == 3
    for s in sessions:
        assert (await session(client, s["room_id"], s["token"]))["seat"] == s["seat"]
    # The host of the new room can start it
    response = await act(client, sessions[0]["room_id"], sessions[0]["token"], "start_game")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_old_tokens_do_not_work_in_the_rematch(client):
    host, _ = await finished_room(client)
    await act(client, host["room_id"], host["token"], "rematch")
    new_id = (await rematch(client, host["room_id"], host["token"])).json()["room_id"]

    response = await act(client, new_id, host["token"], "start_game")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_only_the_host_starts_a_rematch(client):
    host, (guest,) = await finished_room(client)

    response = await act(client, host["room_id"], guest["token"], "rematch")

    assert response.status_code == 400
    assert "host" in response.json()["detail"]
    assert (await session(client, host["room_id"], host["token"]))["public"]["rematch_room_id"] is None


@pytest.mark.asyncio
async def test_rematch_needs_a_finished_game(client):
    host, _ = await started_room(client)
    lobby = await create_room(client)

    playing = await act(client, host["room_id"], host["token"], "rematch")
    waiting = await act(client, lobby["room_id"], lobby["token"], "rematch")

    assert playing.status_code == 400
    assert "not over" in playing.json()["detail"]
    assert waiting.status_code == 400


@pytest.mark.asyncio
async def test_second_rematch_changes_nothing(client):
    host, _ = await finished_room(client)
    await act(client, host["room_id"], host["token"], "rematch")
    before = await app.state.redis.get_room(host["room_id"])

    response = await act(client, host["room_id"], host["token"], "rematch")

    assert response.status_code == 200
    assert await app.state.redis.get_room(host["room_id"]) == before


@pytest.mark.asyncio
async def test_no_rematch_yet(client):
    host, (guest,) = await finished_room(client)

    response = await rematch(client, host["room_id"], guest["token"])

    assert response.status_code == 409
    assert response.json()["detail"] == "There is no rematch yet."


@pytest.mark.asyncio
async def test_rematch_needs_a_valid_session(client):
    host, _ = await finished_room(client)
    await act(client, host["room_id"], host["token"], "rematch")

    assert (await rematch(client, host["room_id"], "forged")).status_code == 401
    assert (await rematch(client, "missing0", host["token"])).status_code == 404


@pytest.mark.asyncio
async def test_bots_play_the_rematch_too(client):
    host, _ = await finished_room(client, guests=(), bots=1)
    old_bot = (await app.state.redis.get_room(host["room_id"]))["seats"][1]["token"]
    await act(client, host["room_id"], host["token"], "rematch")
    new = (await rematch(client, host["room_id"], host["token"])).json()
    state = await session(client, new["room_id"], new["token"])
    assert [p["is_bot"] for p in state["public"]["players"]] == [False, True]

    before = await last_summon()
    await act(client, new["room_id"], new["token"], "start_game")

    (bot,) = await summoned_since(before)
    assert bot["room_id"] == new["room_id"]
    assert bot["token"] != old_bot
    assert (await session(client, new["room_id"], bot["token"]))["seat"] == 1
    await clear_bots()


@pytest.mark.asyncio
async def test_player_replaced_by_a_bot_reclaims_the_rematch_seat_by_name(client):
    host, (bob, charlie) = await finished_room(client, guests=("Bob", "Charlie"))
    room = await app.state.redis.get_room(host["room_id"])
    room["seats"][1].update(bot=True, replaced=True, token="bot-token")
    await app.state.redis.save_room(host["room_id"], room)
    await act(client, host["room_id"], host["token"], "rematch")
    new = (await rematch(client, host["room_id"], host["token"])).json()

    players = (await session(client, new["room_id"], new["token"]))["public"]["players"]
    assert [p["is_bot"] for p in players] == [False, True, False]

    returned = await join(client, new["room_id"], "Bob")

    assert returned.status_code == 200
    assert returned.json()["seat"] == 1
    players = (await session(client, new["room_id"], returned.json()["token"]))["public"]["players"]
    assert players[1]["is_bot"] is False


@pytest.mark.asyncio
async def test_player_back_in_the_old_room_takes_the_seat_from_the_bot(client):
    host, (bob,) = await finished_room(client)
    room = await app.state.redis.get_room(host["room_id"])
    room["seats"][1].update(bot=True, replaced=True, token="bot-token")
    await app.state.redis.save_room(host["room_id"], room)
    await act(client, host["room_id"], host["token"], "rematch")
    # Bob left during the game and only now comes back by name
    returned = (await join(client, host["room_id"], "Bob")).json()

    new = (await rematch(client, host["room_id"], returned["token"])).json()

    assert new["seat"] == 1
    new_room = await app.state.redis.get_room(new["room_id"])
    assert new_room["seats"][1]["token"] == new["token"]
    assert not new_room["seats"][1].get("bot")
    await clear_bots()


@pytest.mark.asyncio
async def test_rematch_tokens_stay_secret(client):
    host, (guest,) = await finished_room(client, bots=1)
    after = await stream_tail()

    await act(client, host["room_id"], host["token"], "rematch")

    raw = await next_event(host["room_id"], after)
    room = await app.state.redis.get_room(host["room_id"])
    hidden = [entry["rematch_token"] for entry in room["seats"]]
    new_id = room["rematch_room_id"]
    texts = [
        raw,
        json.dumps(await session(client, host["room_id"], guest["token"])),
        (await client.get(f"/api/rooms/{host['room_id']}")).text,
        (await client.get(f"/api/rooms/{new_id}")).text,
    ]
    for text in texts:
        assert not any(token in text for token in hidden)
    await clear_bots()


@pytest.mark.asyncio
async def test_bots_keep_their_level_in_the_rematch(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot", {"level": "easy"})
    await act(client, host["room_id"], host["token"], "add_bot", {"level": "hard"})
    bob = (await join(client, host["room_id"], "Bob")).json()
    await act(client, host["room_id"], host["token"], "start_game")
    await finish(client, host)
    room = await app.state.redis.get_room(host["room_id"])
    # Bob left and a bot took over his seat
    room["seats"][bob["seat"]].update(bot=True, replaced=True, level="medium", token="bot-token")
    await app.state.redis.save_room(host["room_id"], room)

    await act(client, host["room_id"], host["token"], "rematch")

    new = (await rematch(client, host["room_id"], host["token"])).json()
    players = (await session(client, new["room_id"], new["token"]))["public"]["players"]
    assert [p["bot_level"] for p in players] == [None, "easy", "hard", "medium"]
    await clear_bots()


@pytest.mark.asyncio
async def test_bots_of_older_rooms_play_the_rematch_at_medium(client):
    host, _ = await finished_room(client, guests=(), bots=1)
    room = await app.state.redis.get_room(host["room_id"])
    del room["seats"][1]["level"]
    await app.state.redis.save_room(host["room_id"], room)

    await act(client, host["room_id"], host["token"], "rematch")

    new_id = (await app.state.redis.get_room(host["room_id"]))["rematch_room_id"]
    assert (await app.state.redis.get_room(new_id))["seats"][1]["level"] == "medium"
    await clear_bots()
