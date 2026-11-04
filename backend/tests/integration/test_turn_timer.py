from unittest.mock import patch

import pytest
import pytest_asyncio

from app.main import app
from app.models.board import ResourceType
from app.models.game import Building, BuildingType, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.models.player import DevCard
from app.services.redis_service import TURN_DEADLINES_KEY
from rooms_api import CENTER, HEADERS, act, create_room, edit_game, join, load_game, past_setup, session

START = 1_000_000.0
NEAR = Hex(1, -1, 0)


@pytest_asyncio.fixture
async def clock(client):
    """Stops the room clock at START; tests move it by setting `clock.now`."""
    class Clock:
        now = START

    app.state.rooms.clock = lambda: Clock.now
    yield Clock
    # Leftover rooms would keep the bot service of a running dev setup busy
    await app.state.redis.redis.delete(TURN_DEADLINES_KEY)


async def timed_room(client, players=("Bob",), seconds=60):
    host = await create_room(client)
    guests = [(await join(client, host["room_id"], name)).json() for name in players]
    if seconds:
        await act(client, host["room_id"], host["token"], "update_settings", {"turn_seconds": seconds})
    assert (await act(client, host["room_id"], host["token"], "start_game")).status_code == 200
    return host, guests


async def time_out(client, room_id, headers=HEADERS):
    return await client.post(f"/internal/rooms/{room_id}/timeout", headers=headers)


async def deadline_score(room_id):
    return await app.state.redis.redis.zscore(TURN_DEADLINES_KEY, room_id)


@pytest.mark.asyncio
async def test_lobby_has_no_deadline(client, clock):
    host = await create_room(client)

    public = (await session(client, host["room_id"], host["token"]))["public"]

    assert public["turn_deadline"] is None
    assert isinstance(public["server_time"], float)
    assert await deadline_score(host["room_id"]) is None


@pytest.mark.asyncio
async def test_starting_sets_the_first_deadline(client, clock):
    host, _ = await timed_room(client, seconds=90)

    public = (await session(client, host["room_id"], host["token"]))["public"]

    assert public["turn_deadline"] == START + 90
    assert await deadline_score(host["room_id"]) == START + 90


@pytest.mark.asyncio
async def test_without_a_time_limit_there_is_no_deadline(client, clock):
    host, _ = await timed_room(client, seconds=None)

    public = (await session(client, host["room_id"], host["token"]))["public"]

    assert public["turn_deadline"] is None
    assert await deadline_score(host["room_id"]) is None
    assert (await time_out(client, host["room_id"])).json() == {"ok": True, "finished": False}


@pytest.mark.asyncio
async def test_deadline_moves_only_with_the_turn_or_its_step(client, clock):
    host, _ = await timed_room(client)
    room_id = host["room_id"]
    clock.now = START + 10

    await act(client, room_id, host["token"], "build_settlement", {"hex": CENTER, "direction": 0})

    # Still the same setup turn
    assert (await session(client, room_id, host["token"]))["public"]["turn_deadline"] == START + 60

    edge = (await session(client, room_id, host["token"]))["private"]["legal"]["roads"][0]
    await act(client, room_id, host["token"], "build_road", edge)

    assert (await session(client, room_id, host["token"]))["public"]["turn_deadline"] == START + 70
    assert await deadline_score(room_id) == START + 70


@pytest.mark.asyncio
async def test_timeout_before_the_deadline_does_nothing(client, clock):
    host, _ = await timed_room(client)
    before = await app.state.redis.get_room(host["room_id"])
    clock.now = START + 59

    response = await time_out(client, host["room_id"])

    assert response.status_code == 200
    assert response.json() == {"ok": True, "finished": False}
    assert await app.state.redis.get_room(host["room_id"]) == before


@pytest.mark.asyncio
async def test_timeout_after_the_deadline_finishes_the_turn(client, clock):
    host, (guest,) = await timed_room(client)
    clock.now = START + 60

    response = await time_out(client, host["room_id"])

    assert response.json() == {"ok": True, "finished": True}
    state = await session(client, host["room_id"], guest["token"])
    assert state["public"]["game"]["current_seat"] == 1
    assert state["public"]["game"]["log"][0] == "Alice ran out of time."
    assert state["public"]["turn_deadline"] == START + 120
    assert await deadline_score(host["room_id"]) == START + 120


@pytest.mark.asyncio
async def test_repeated_timeout_finishes_only_one_turn(client, clock):
    host, _ = await timed_room(client)
    clock.now = START + 61

    first = await time_out(client, host["room_id"])
    second = await time_out(client, host["room_id"])

    assert first.json()["finished"] is True
    assert second.json()["finished"] is False
    assert (await load_game(host["room_id"])).turn_number == 1


@pytest.mark.asyncio
async def test_timeout_needs_the_internal_key(client, clock):
    host, _ = await timed_room(client)
    clock.now = START + 600

    response = await time_out(client, host["room_id"], headers={"X-Internal-Key": "wrong"})

    assert response.status_code == 403
    assert (await load_game(host["room_id"])).turn_number == 0


@pytest.mark.asyncio
async def test_timeout_of_a_room_that_is_gone_clears_it(client, clock):
    await app.state.redis.set_turn_deadline("gone0000", START)

    response = await time_out(client, "gone0000")

    assert response.json() == {"ok": True, "finished": False}
    assert await deadline_score("gone0000") is None


@pytest.mark.asyncio
async def test_timeout_of_a_lobby_clears_it(client, clock):
    host = await create_room(client)
    await app.state.redis.set_turn_deadline(host["room_id"], START)

    response = await time_out(client, host["room_id"])

    assert response.json()["finished"] is False
    assert await deadline_score(host["room_id"]) is None


def roll_phase(game):
    past_setup(game)


def main_phase_with_offer(game):
    past_setup(game)
    game.turn_phase = TurnPhase.MAIN_PHASE
    alice = game.players[0]
    alice.add_resource(ResourceType.WOOD, 1)
    game.offer_trade(alice, {ResourceType.WOOD: 1}, {ResourceType.ORE: 1})


def discard_by_several(game):
    past_setup(game)
    game.turn_phase = TurnPhase.DISCARD
    game.dice_roll = 7
    for player in game.players[1:]:
        player.add_resource(ResourceType.ORE, 9)
        game.pending_discards[player.color] = 4


def move_robber(game):
    past_setup(game)
    game.turn_phase = TurnPhase.MOVE_ROBBER


def steal(game):
    past_setup(game)
    bob = game.players[1]
    game.robber_hex = NEAR
    game.settlements[Vertex(NEAR, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
    bob.add_resource(ResourceType.SHEEP, 2)
    game.turn_phase = TurnPhase.STEAL


def road_building(game):
    past_setup(game)
    game.turn_phase = TurnPhase.MAIN_PHASE
    alice = game.players[0]
    alice.dev_cards = [DevCard.ROAD_BUILDING]
    game.play_road_building(alice)


def setup_road(game):
    alice = game.players[0]
    game.place_settlement(alice, Vertex(Hex(0, 0, 0), 0))


@pytest.mark.asyncio
@pytest.mark.parametrize("prepare", [
    setup_road, roll_phase, main_phase_with_offer, discard_by_several, move_robber, steal, road_building,
])
async def test_timeout_finishes_every_blocking_step(client, clock, prepare):
    host, guests = await timed_room(client, players=("Bob", "Charlie"))
    room_id = host["room_id"]
    await edit_game(room_id, prepare)
    clock.now = START + 60

    with patch("random.randint", side_effect=[2, 3]):
        response = await time_out(client, room_id)

    assert response.json()["finished"] is True
    game = await load_game(room_id)
    assert game.current_turn_index == 1
    assert game.turn_number == 1
    assert game.trade_offer is None
    assert game.pending_discards == {}
    assert game.free_roads_left == 0
    assert game.turn_phase in (TurnPhase.SETUP, TurnPhase.ROLL_DICE)


@pytest.mark.asyncio
async def test_discards_of_every_waiting_player_are_made(client, clock):
    host, (bob, charlie) = await timed_room(client, players=("Bob", "Charlie"))
    room_id = host["room_id"]
    await edit_game(room_id, discard_by_several)
    clock.now = START + 60

    await time_out(client, room_id)

    game = await load_game(room_id)
    # Each had 9 ore and gave up 4; Alice may then have stolen one of what was left
    assert [p.card_count() for p in game.players[1:]] in ([5, 5], [4, 5], [5, 4])
    log = game.log
    assert "Bob ran out of time." in log
    assert "Charlie ran out of time." in log
    assert "Bob discarded 4 cards." in log
    assert "Charlie discarded 4 cards." in log


@pytest.mark.asyncio
async def test_timeout_that_ends_the_game_stops_the_timer(client, clock):
    host, _ = await timed_room(client)
    room_id = host["room_id"]

    def about_to_win(game):
        main_phase_with_offer(game)
        game.players[0].dev_cards = [DevCard.VICTORY_POINT] * 9

    await edit_game(room_id, about_to_win)
    clock.now = START + 60

    response = await time_out(client, room_id)

    assert response.json()["finished"] is True
    public = (await session(client, room_id, host["token"]))["public"]
    assert public["status"] == "finished"
    assert public["game"]["winner_seat"] == 0
    assert public["turn_deadline"] is None
    assert await deadline_score(room_id) is None
    assert (await time_out(client, room_id)).json()["finished"] is False
