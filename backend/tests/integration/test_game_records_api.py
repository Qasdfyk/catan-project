"""
Records of real games: written while the game runs, saved when it ends,
downloadable afterwards, and replaying to exactly the game the server stored.
"""
import asyncio
import random

import pytest

from app.main import app
from app.services.game_record import fingerprint, replay
from app.services.random_player import play_step
from rooms_api import act, create_room, join, load_game, started_room


async def play_to_the_end(client, room_id, tokens, seed=3):
    """
    Plays random legal moves through the API, as players would. Each move is
    found on a copy of the stored game; the server then decides it again,
    rolling its own dice.
    """
    rng = random.Random(seed)
    for _ in range(10_000):
        game = await load_game(room_id)
        if game.is_game_over:
            return game
        play_step(game, rng)
        for event in game.take_events():
            response = await act(client, room_id, tokens[event["seat"]], event["action"], event["payload"])
            assert response.status_code == 200, (event, response.text)
    raise AssertionError("the game did not end")


async def download(client, room_id):
    return await client.get(f"/api/rooms/{room_id}/record")


@pytest.mark.asyncio
async def test_finished_game_downloads_and_replays(client):
    host, guest = await started_room(client)
    room_id = host["room_id"]

    stored = await play_to_the_end(client, room_id, [host["token"], guest["token"]])
    response = await download(client, room_id)

    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="catan-{room_id}.json"'
    record = response.json()
    assert (record["source"], record["game_id"]) == ("platform", room_id)
    assert record["result"]["winner_seat"] == stored.seat_of(stored.winner)
    assert record["finished_at"] is not None
    # Every change the server made is in the record, and nothing else
    assert fingerprint(replay(record)) == fingerprint(stored)


@pytest.mark.asyncio
async def test_saved_record_leaves_redis_and_outlives_the_room(client):
    host, guest = await started_room(client)
    room_id = host["room_id"]
    await play_to_the_end(client, room_id, [host["token"], guest["token"]], seed=5)

    assert await app.state.redis.load_record(room_id) is None
    assert app.state.rooms.records.path(room_id).exists()

    # Redis forgets the room after a day; the file stays
    await app.state.redis.redis.delete(f"room:{room_id}", f"game:{room_id}")
    assert (await download(client, room_id)).status_code == 200


@pytest.mark.asyncio
async def test_no_record_while_the_game_runs(client):
    host, _ = await started_room(client)
    response = await download(client, host["room_id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "The game is not over yet."


@pytest.mark.asyncio
async def test_lobby_has_no_record(client):
    host = await create_room(client)
    assert (await download(client, host["room_id"])).status_code == 409


@pytest.mark.parametrize("room_id", ["nosuchroom", "a.b", "..", "x" * 65])
@pytest.mark.asyncio
async def test_unknown_or_invalid_room_is_not_found(client, room_id):
    assert (await download(client, room_id)).status_code == 404


@pytest.mark.asyncio
async def test_record_grows_with_every_action(client):
    host, guest = await started_room(client)
    room_id = host["room_id"]

    record = await app.state.redis.load_record(room_id)
    assert record["events"] == []
    assert [p["kind"] for p in record["players"]] == ["human", "human"]

    await play_step_once(client, room_id, [host["token"], guest["token"]])
    events = (await app.state.redis.load_record(room_id))["events"]
    assert [e["action"] for e in events] == ["build_settlement"]


async def play_step_once(client, room_id, tokens):
    game = await load_game(room_id)
    play_step(game, random.Random(1))
    for event in game.take_events():
        assert (await act(client, room_id, tokens[event["seat"]], event["action"], event["payload"])).status_code == 200


@pytest.mark.asyncio
async def test_refused_action_adds_no_event(client):
    host, guest = await started_room(client)
    room_id = host["room_id"]

    # The guest is not on turn
    response = await act(client, room_id, guest["token"], "roll_dice")
    assert response.status_code == 400
    assert (await app.state.redis.load_record(room_id))["events"] == []


@pytest.mark.asyncio
async def test_bot_seats_are_marked(client):
    host = await create_room(client)
    room_id = host["room_id"]
    await join(client, room_id, "Bob")
    await act(client, room_id, host["token"], "add_bot", {"level": "hard"})
    await act(client, room_id, host["token"], "start_game")

    players = (await app.state.redis.load_record(room_id))["players"]
    assert [(p["kind"], p["bot_level"]) for p in players] == [("human", None), ("human", None), ("bot", "hard")]


@pytest.mark.asyncio
async def test_failed_save_still_ends_the_game(client, monkeypatch):
    host, guest = await started_room(client)
    room_id = host["room_id"]

    def broken_disk(*_):
        raise OSError("disk full")

    monkeypatch.setattr(app.state.rooms.records, "save", broken_disk)
    await play_to_the_end(client, room_id, [host["token"], guest["token"]], seed=5)

    room = await app.state.redis.get_room(room_id)
    assert room["status"] == "finished"
    assert not room["record_saved"]
    # Kept in Redis for the next try
    assert (await app.state.redis.load_record(room_id))["result"] is None


def broken_disk(*_):
    raise OSError("disk full")


async def finish_without_saving(client, monkeypatch, seed=5):
    host, guest = await started_room(client)
    room_id = host["room_id"]
    with monkeypatch.context() as patch:
        patch.setattr(app.state.rooms.records, "save", broken_disk)
        stored = await play_to_the_end(client, room_id, [host["token"], guest["token"]], seed=seed)
    return host, stored


@pytest.mark.asyncio
async def test_download_retries_a_failed_save(client, monkeypatch):
    host, stored = await finish_without_saving(client, monkeypatch)
    room_id = host["room_id"]

    response = await download(client, room_id)

    assert response.status_code == 200
    assert fingerprint(replay(response.json())) == fingerprint(stored)
    assert (await app.state.redis.get_room(room_id))["record_saved"]
    assert app.state.rooms.records.path(room_id).exists()
    assert await app.state.redis.load_record(room_id) is None


@pytest.mark.asyncio
async def test_download_serves_the_record_while_the_disk_still_fails(client, monkeypatch):
    host, stored = await finish_without_saving(client, monkeypatch)
    room_id = host["room_id"]
    monkeypatch.setattr(app.state.rooms.records, "save", broken_disk)

    response = await download(client, room_id)

    assert response.status_code == 200
    record = response.json()
    assert record["result"]["winner_seat"] == stored.seat_of(stored.winner)
    assert fingerprint(replay(record)) == fingerprint(stored)
    # Still in Redis for the next try
    assert not (await app.state.redis.get_room(room_id))["record_saved"]
    assert (await app.state.redis.load_record(room_id))["result"] is None


@pytest.mark.asyncio
async def test_rematch_retries_a_failed_save(client, monkeypatch):
    host, stored = await finish_without_saving(client, monkeypatch)
    room_id = host["room_id"]

    assert (await act(client, room_id, host["token"], "rematch")).status_code == 200

    assert (await app.state.redis.get_room(room_id))["record_saved"]
    assert app.state.rooms.records.path(room_id).exists()


@pytest.mark.asyncio
async def test_parallel_downloads_save_once(client, monkeypatch):
    host, stored = await finish_without_saving(client, monkeypatch)
    room_id = host["room_id"]
    saves = []
    real_save = app.state.rooms.records.save
    monkeypatch.setattr(app.state.rooms.records, "save", lambda *args: (saves.append(1), real_save(*args)))

    responses = await asyncio.gather(*(download(client, room_id) for _ in range(5)))

    assert [r.status_code for r in responses] == [200] * 5
    assert len({r.text for r in responses}) == 1
    assert len(saves) == 1
