import asyncio
import json

import pytest

from app.models.game import GameState
from app.models.player import DevCard
from app.models.settings import GameSettings
from app.services.serializer import GameSerializer
from app.services.views import public_view
from app.main import app
from rooms_api import (
    CENTER, act, clear_bots, create_room, join, last_summon, lasting_state, next_event, session, started_room,
    stream_tail, summoned_since,
)


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
    after = await stream_tail()

    await act(client, host["room_id"], host["token"], "build_settlement", {"hex": CENTER, "direction": 0})

    raw = await next_event(host["room_id"], after)
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
    before = await lasting_state(client, host["room_id"], host["token"])

    await act(client, host["room_id"], host["token"], "roll_dice")

    assert await lasting_state(client, host["room_id"], host["token"]) == before


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
    before = await last_summon()

    response = await act(client, host["room_id"], host["token"], "start_game")

    assert response.status_code == 200
    (bot,) = await summoned_since(before)
    assert bot["room_id"] == host["room_id"]
    state = await session(client, host["room_id"], bot["token"])
    assert state["seat"] == 1
    await clear_bots()


@pytest.mark.asyncio
async def test_bots_play_at_the_level_chosen_for_them(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    await act(client, host["room_id"], host["token"], "add_bot", {"level": "easy"})
    await act(client, host["room_id"], host["token"], "set_bot_level", {"seat": 1, "level": "hard"})
    guest = (await join(client, host["room_id"], "Bob")).json()

    players = (await session(client, host["room_id"], guest["token"]))["public"]["players"]
    assert [p["bot_level"] for p in players] == [None, "hard", "easy", None]

    await act(client, host["room_id"], host["token"], "start_game")

    players = (await session(client, host["room_id"], guest["token"]))["public"]["players"]
    assert [p["bot_level"] for p in players] == [None, "hard", "easy", None]
    await clear_bots()


@pytest.mark.asyncio
async def test_summoned_bots_know_their_level(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot", {"level": "easy"})
    await act(client, host["room_id"], host["token"], "add_bot")
    room = await app.state.redis.get_room(host["room_id"])
    before = await last_summon()

    await act(client, host["room_id"], host["token"], "start_game")

    assert await summoned_since(before) == [
        {"room_id": host["room_id"], "token": room["seats"][1]["token"], "level": "easy"},
        {"room_id": host["room_id"], "token": room["seats"][2]["token"], "level": "medium"},
    ]
    await clear_bots()


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["expert", "", None, 2, ["easy"]])
async def test_bot_level_must_be_known(client, level):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")

    added = await act(client, host["room_id"], host["token"], "add_bot", {"level": level})
    changed = await act(client, host["room_id"], host["token"], "set_bot_level", {"seat": 1, "level": level})

    for response in (added, changed):
        assert response.status_code == 400
        assert response.json()["detail"] == "Choose easy, medium or hard."
    players = (await session(client, host["room_id"], host["token"]))["public"]["players"]
    assert [p["bot_level"] for p in players] == [None, "medium"]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [0, 2, True, None, "1"])
async def test_level_is_set_only_on_bot_seats(client, target):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")

    response = await act(client, host["room_id"], host["token"], "set_bot_level", {"seat": target, "level": "easy"})

    assert response.status_code == 400
    assert response.json()["detail"] == "That seat has no bot."


@pytest.mark.asyncio
async def test_only_the_host_sets_bot_levels_in_the_lobby(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    guest = (await join(client, host["room_id"], "Bob")).json()

    by_guest = await act(client, host["room_id"], guest["token"], "set_bot_level", {"seat": 1, "level": "easy"})
    await act(client, host["room_id"], host["token"], "start_game")
    after_start = await act(client, host["room_id"], host["token"], "set_bot_level", {"seat": 1, "level": "easy"})

    assert by_guest.status_code == 400
    assert "host" in by_guest.json()["detail"]
    assert after_start.status_code == 400
    assert "started" in after_start.json()["detail"]
    players = (await session(client, host["room_id"], host["token"]))["public"]["players"]
    assert players[1]["bot_level"] == "medium"
    await clear_bots()


def test_bots_of_older_rooms_play_at_medium():
    room = {"room_id": "r", "version": 1, "status": "lobby", "host_seat": 0,
            "seats": [{"name": "Alice"}, {"name": "Ada", "bot": True}]}

    assert [p["bot_level"] for p in public_view(room, None)["players"]] == [None, "medium"]


@pytest.mark.asyncio
async def test_bots_of_older_rooms_are_summoned_at_medium(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    room = await app.state.redis.get_room(host["room_id"])
    del room["seats"][1]["level"]
    await app.state.redis.save_room(host["room_id"], room)
    before = await last_summon()

    await act(client, host["room_id"], host["token"], "start_game")

    assert [bot["level"] for bot in await summoned_since(before)] == ["medium"]
    await clear_bots()


@pytest.mark.asyncio
async def test_bot_tokens_stay_out_of_public_state(client):
    host = await create_room(client)
    await act(client, host["room_id"], host["token"], "add_bot")
    await act(client, host["room_id"], host["token"], "start_game")
    room = await app.state.redis.get_room(host["room_id"])
    bot_token = room["seats"][1]["token"]

    state = await session(client, host["room_id"], host["token"])

    assert bot_token not in json.dumps(state)
    await clear_bots()


def test_hidden_points_are_revealed_only_when_the_game_ends():
    game = GameState.create_new_game(["Alice", "Bob"])
    game.players[0].dev_cards = [DevCard.VICTORY_POINT]
    room = {"room_id": "r", "version": 1, "status": "playing", "host_seat": 0,
            "seats": [{"name": "Alice"}, {"name": "Bob"}]}

    assert public_view(room, game)["players"][0]["victory_points"] == 0

    game.is_game_over = True

    assert public_view(room, game)["players"][0]["victory_points"] == 1


@pytest.mark.asyncio
async def test_bot_can_take_over_a_seat_of_a_player_who_left(client):
    host, guest = await started_room(client)

    response = await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})

    assert response.status_code == 200
    state = await session(client, host["room_id"], host["token"])
    assert state["public"]["players"][guest["seat"]]["is_bot"] is True
    assert state["public"]["players"][guest["seat"]]["bot_level"] == "medium"
    assert (await act(client, host["room_id"], guest["token"], "end_turn")).status_code == 401
    await clear_bots()


@pytest.mark.asyncio
async def test_bot_taking_over_a_seat_plays_at_medium(client):
    host, guest = await started_room(client)
    before = await last_summon()

    await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})

    token = (await app.state.redis.get_room(host["room_id"]))["seats"][guest["seat"]]["token"]
    bot = {"room_id": host["room_id"], "token": token, "level": "medium"}
    assert await summoned_since(before) == [bot]
    await clear_bots()


@pytest.mark.asyncio
async def test_connected_player_cannot_be_replaced(client):
    host, guest = await started_room(client)
    redis = app.state.redis.redis
    key = f"presence:{host['room_id']}:{guest['seat']}"
    await redis.set(key, "1", ex=30)

    response = await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})

    await redis.delete(key)
    assert response.status_code == 400
    assert "connected" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [0, 9, True, None, "1"])
async def test_replacing_needs_another_valid_seat(client, target):
    host, _ = await started_room(client)

    response = await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": target})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_replacing_needs_a_running_game(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()

    response = await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_player_takes_the_seat_back_from_the_bot(client):
    host, guest = await started_room(client)
    await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})
    room = await app.state.redis.get_room(host["room_id"])
    bot_token = room["seats"][guest["seat"]]["token"]

    returned = await join(client, host["room_id"], "Bob")

    assert returned.status_code == 200
    assert returned.json()["seat"] == guest["seat"]
    state = await session(client, host["room_id"], returned.json()["token"])
    assert state["public"]["players"][guest["seat"]]["is_bot"] is False
    assert state["public"]["players"][guest["seat"]]["bot_level"] is None
    assert (await act(client, host["room_id"], bot_token, "end_turn")).status_code == 401
    await clear_bots()


@pytest.mark.asyncio
async def test_seat_held_by_a_bot_shows_as_free_on_the_join_screen(client):
    host, guest = await started_room(client)
    await act(client, host["room_id"], host["token"], "replace_with_bot", {"seat": guest["seat"]})
    redis = app.state.redis.redis
    key = f"presence:{host['room_id']}:{guest['seat']}"
    await redis.set(key, "1", ex=30)

    summary = await client.get(f"/api/rooms/{host['room_id']}")

    await redis.delete(key)
    assert summary.json()["players"][guest["seat"]]["online"] is False
    await clear_bots()


@pytest.mark.asyncio
async def test_new_room_has_the_standard_settings(client):
    host = await create_room(client)

    state = await session(client, host["room_id"], host["token"])

    assert state["public"]["settings"] == GameSettings().to_dict()


@pytest.mark.asyncio
async def test_host_changes_settings_one_key_at_a_time(client):
    host = await create_room(client)

    await act(client, host["room_id"], host["token"], "update_settings", {"victory_points": 12})
    response = await act(client, host["room_id"], host["token"], "update_settings", {"friendly_robber": True})

    assert response.status_code == 200
    settings = (await session(client, host["room_id"], host["token"]))["public"]["settings"]
    assert settings == {**GameSettings().to_dict(), "victory_points": 12, "friendly_robber": True}


@pytest.mark.asyncio
async def test_guest_cannot_change_settings(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()

    response = await act(client, host["room_id"], guest["token"], "update_settings", {"victory_points": 6})

    assert response.status_code == 400
    assert "host" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"victory_points": 20}, {"desert": "edge"}, {"speed": 2}])
async def test_invalid_settings_change_nothing(client, payload):
    host = await create_room(client)
    before = await lasting_state(client, host["room_id"], host["token"])

    response = await act(client, host["room_id"], host["token"], "update_settings", payload)

    assert response.status_code == 400
    assert await lasting_state(client, host["room_id"], host["token"]) == before


@pytest.mark.asyncio
async def test_settings_are_frozen_once_the_game_starts(client):
    host, _ = await started_room(client)

    response = await act(client, host["room_id"], host["token"], "update_settings", {"victory_points": 6})

    assert response.status_code == 400
    assert "already started" in response.json()["detail"]


@pytest.mark.asyncio
async def test_settings_reach_the_started_game(client):
    host = await create_room(client)
    await join(client, host["room_id"], "Bob")
    chosen = {"victory_points": 8, "discard_limit": 9, "desert": "center",
              "friendly_robber": True, "turn_seconds": 120}
    await act(client, host["room_id"], host["token"], "update_settings", chosen)

    await act(client, host["room_id"], host["token"], "start_game")

    state = await session(client, host["room_id"], host["token"])
    assert state["public"]["settings"] == chosen
    assert state["public"]["game"]["robber_hex"] == CENTER
    game = GameSerializer.dict_to_game(await app.state.redis.get_game_state(host["room_id"]))
    assert game.settings == GameSettings(**chosen)


@pytest.mark.asyncio
async def test_rooms_saved_before_settings_existed_still_start(client):
    host = await create_room(client)
    await join(client, host["room_id"], "Bob")
    room = await app.state.redis.get_room(host["room_id"])
    del room["settings"]
    await app.state.redis.save_room(host["room_id"], room)

    await act(client, host["room_id"], host["token"], "update_settings", {"discard_limit": 5})
    response = await act(client, host["room_id"], host["token"], "start_game")

    assert response.status_code == 200
    settings = (await session(client, host["room_id"], host["token"]))["public"]["settings"]
    assert settings == {**GameSettings().to_dict(), "discard_limit": 5}
