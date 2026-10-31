import asyncio
import json

import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.main import app
from app.services.redis_service import ACTIVE_BOTS_KEY, BOTS_CHANNEL, EVENTS_CHANNEL, RedisService
from app.services.room_service import RoomService

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}
CENTER = {"q": 0, "r": 0, "s": 0}


@pytest_asyncio.fixture
async def client():
    # httpx does not run the lifespan, so the app state is set up here
    app.state.redis = RedisService()
    app.state.rooms = RoomService(app.state.redis)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await app.state.redis.close()


async def create_room(client, name="Alice"):
    response = await client.post("/api/rooms", json={"name": name})
    assert response.status_code == 200
    return response.json()


async def join(client, room_id, name):
    return await client.post(f"/api/rooms/{room_id}/join", json={"name": name})


async def act(client, room_id, token, action, payload=None):
    return await client.post(
        f"/internal/rooms/{room_id}/actions",
        json={"token": token, "type": action, "payload": payload or {}},
        headers=HEADERS,
    )


async def session(client, room_id, token):
    response = await client.post(
        f"/internal/rooms/{room_id}/session", json={"token": token}, headers=HEADERS
    )
    assert response.status_code == 200
    return response.json()


async def started_room(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()
    response = await act(client, host["room_id"], host["token"], "start_game")
    assert response.status_code == 200
    return host, guest


@pytest.mark.asyncio
async def test_health_is_reachable(client):
    """Regression: the socket app mounted on / made /health unreachable."""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_every_player_gets_their_own_seat(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()

    assert host["seat"] == 0
    assert guest["seat"] == 1
    assert guest["token"] != host["token"]


@pytest.mark.asyncio
async def test_join_validates_the_name(client):
    host = await create_room(client)

    response = await join(client, host["room_id"], "   ")

    assert response.status_code == 422
    assert "between 1 and 20" in response.json()["detail"]


@pytest.mark.asyncio
async def test_join_unknown_room(client):
    response = await join(client, "missing0", "Bob")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_room_is_limited_to_four_players(client):
    host = await create_room(client)
    for name in ("B", "C", "D"):
        assert (await join(client, host["room_id"], name)).status_code == 200

    response = await join(client, host["room_id"], "E")

    assert response.status_code == 409
    assert "full" in response.json()["detail"]


@pytest.mark.asyncio
async def test_only_host_starts_the_game(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()

    response = await act(client, host["room_id"], guest["token"], "start_game")

    assert response.status_code == 400
    assert "host" in response.json()["detail"]


@pytest.mark.asyncio
async def test_game_needs_two_players(client):
    host = await create_room(client)

    response = await act(client, host["room_id"], host["token"], "start_game")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_new_players_cannot_join_a_running_game(client):
    host, _ = await started_room(client)

    response = await join(client, host["room_id"], "Charlie")

    assert response.status_code == 409
    assert "already started" in response.json()["detail"]


@pytest.mark.asyncio
async def test_player_returns_by_name_and_old_session_stops_working(client):
    host, guest = await started_room(client)

    rejoined = await join(client, host["room_id"], "bob")

    assert rejoined.status_code == 200
    assert rejoined.json()["seat"] == guest["seat"]
    stale = await act(client, host["room_id"], guest["token"], "end_turn")
    assert stale.status_code == 401


@pytest.mark.asyncio
async def test_connected_seat_cannot_be_taken_over(client):
    host, guest = await started_room(client)
    redis = app.state.redis.redis
    key = f"presence:{host['room_id']}:{guest['seat']}"
    await redis.set(key, "1", ex=30)

    response = await join(client, host["room_id"], "Bob")

    await redis.delete(key)
    assert response.status_code == 409
    assert (await session(client, host["room_id"], guest["token"]))["seat"] == guest["seat"]


@pytest.mark.asyncio
async def test_action_is_performed_as_the_token_owner(client):
    """Regression: the server used to act as whoever's turn it was."""
    host, guest = await started_room(client)
    vertex = {"hex": CENTER, "direction": 0}

    response = await act(client, host["room_id"], guest["token"], "build_settlement", vertex)

    assert response.status_code == 400
    assert "not your turn" in response.json()["detail"]
    assert (await act(client, host["room_id"], host["token"], "build_settlement", vertex)).status_code == 200


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(client):
    host, _ = await started_room(client)

    response = await act(client, host["room_id"], "forged", "roll_dice")

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {},
    {"hex": CENTER},
    {"hex": CENTER, "direction": 6},
    {"hex": CENTER, "direction": True},
    {"hex": {"q": 1, "r": 1, "s": 1}, "direction": 0},
    {"hex": "x", "direction": 0},
])
async def test_malformed_payload_gives_a_clean_error(client, payload):
    host, _ = await started_room(client)

    response = await act(client, host["room_id"], host["token"], "build_settlement", payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid position."


@pytest.mark.asyncio
async def test_unknown_action_is_rejected(client):
    host, _ = await started_room(client)

    response = await act(client, host["room_id"], host["token"], "give_me_cards")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_internal_endpoints_need_the_key(client):
    host, _ = await started_room(client)

    response = await client.post(
        f"/internal/rooms/{host['room_id']}/session", json={"token": host["token"]}
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_views_hide_tokens_and_other_hands(client):
    """Regression: player IDs were broadcast to everyone in the game state."""
    host, guest = await started_room(client)
    pubsub = app.state.redis.redis.pubsub()
    await pubsub.subscribe(EVENTS_CHANNEL)
    await pubsub.get_message(timeout=1)

    await act(client, host["room_id"], host["token"], "build_settlement", {"hex": CENTER, "direction": 0})

    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    await pubsub.aclose()
    raw = message["data"]
    event = json.loads(raw)
    assert host["token"] not in raw
    assert guest["token"] not in raw
    assert "resources" not in json.dumps(event["public"])
    assert set(event["private"]) == {"0", "1"}

    state = await session(client, host["room_id"], guest["token"])
    assert host["token"] not in json.dumps(state)
    assert state["private"]["seat"] == guest["seat"]


@pytest.mark.asyncio
async def test_summary_has_no_secrets(client):
    host = await create_room(client)

    response = await client.get(f"/api/rooms/{host['room_id']}")

    assert response.json()["players"] == [{"name": "Alice", "online": False}]
    assert host["token"] not in response.text


@pytest.mark.asyncio
async def test_legal_moves_are_sent_only_to_the_current_player(client):
    host, guest = await started_room(client)

    mine = await session(client, host["room_id"], host["token"])
    theirs = await session(client, host["room_id"], guest["token"])

    assert len(mine["private"]["legal"]["settlements"]) == 54
    assert theirs["private"]["legal"]["settlements"] == []


@pytest.mark.asyncio
async def test_concurrent_actions_do_not_lose_updates(client):
    host = await create_room(client)
    # The room lock must keep parallel joins from overwriting each other
    results = await asyncio.gather(*(join(client, host["room_id"], n) for n in ("B", "C", "D")))

    assert [r.status_code for r in results] == [200, 200, 200]
    summary = await client.get(f"/api/rooms/{host['room_id']}")
    assert len(summary.json()["players"]) == 4


@pytest.mark.asyncio
async def test_version_grows_with_every_change(client):
    host, _ = await started_room(client)
    before = (await session(client, host["room_id"], host["token"]))["public"]["version"]

    await act(client, host["room_id"], host["token"], "build_settlement", {"hex": CENTER, "direction": 0})

    after = (await session(client, host["room_id"], host["token"]))["public"]["version"]
    assert after == before + 1


@pytest.mark.asyncio
async def test_rejected_action_changes_nothing(client):
    host, _ = await started_room(client)
    before = await session(client, host["room_id"], host["token"])

    await act(client, host["room_id"], host["token"], "roll_dice")

    assert await session(client, host["room_id"], host["token"]) == before


@pytest.mark.asyncio
async def test_host_adds_and_removes_bots(client):
    host = await create_room(client)

    await act(client, host["room_id"], host["token"], "add_bot")
    await act(client, host["room_id"], host["token"], "add_bot")
    state = await session(client, host["room_id"], host["token"])
    assert [p["is_bot"] for p in state["public"]["players"]] == [False, True, True]

    await act(client, host["room_id"], host["token"], "remove_bot", {"seat": 2})

    state = await session(client, host["room_id"], host["token"])
    assert len(state["public"]["players"]) == 2


@pytest.mark.asyncio
async def test_removing_a_bot_never_shifts_seats(client):
    """The gateway keeps each connection's seat, so a later player must not move."""
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    guest = (await join(client, host["room_id"], "Bob")).json()

    response = await act(client, host["room_id"], host["token"], "remove_bot", {"seat": 1})

    assert response.status_code == 400
    assert (await session(client, host["room_id"], guest["token"]))["seat"] == 2


@pytest.mark.asyncio
async def test_guest_cannot_add_bots(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()

    response = await act(client, host["room_id"], guest["token"], "add_bot")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_only_bots_can_be_removed(client):
    host = await create_room(client)
    await join(client, host["room_id"], "Bob")

    response = await act(client, host["room_id"], host["token"], "remove_bot", {"seat": 1})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_bot_seat_cannot_be_taken_by_name(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")

    response = await join(client, host["room_id"], "Ada")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_starting_summons_bots_with_their_tokens(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    redis = app.state.redis.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe(BOTS_CHANNEL)
    await pubsub.get_message(timeout=1)

    response = await act(client, host["room_id"], host["token"], "start_game")

    assert response.status_code == 200
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
    await pubsub.aclose()
    bot = json.loads(message["data"])
    assert bot["room_id"] == host["room_id"]
    state = await session(client, host["room_id"], bot["token"])
    assert state["seat"] == 1
    await redis.srem(ACTIVE_BOTS_KEY, message["data"])


@pytest.mark.asyncio
async def test_bot_tokens_stay_out_of_public_state(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    await act(client, host["room_id"], host["token"], "start_game")
    room = await app.state.redis.get_room(host["room_id"])
    bot_token = room["seats"][1]["token"]

    state = await session(client, host["room_id"], host["token"])

    assert bot_token not in json.dumps(state)
    await app.state.redis.redis.delete(ACTIVE_BOTS_KEY)
