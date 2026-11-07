"""Requests the gateway and the browser make, shared by the integration tests."""
import json

from app.core.config import settings
from app.main import app
from app.models.game import Building, BuildingType, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.services.redis_service import EVENTS_STREAM
from app.services.serializer import GameSerializer

HEADERS = {"X-Internal-Key": settings.INTERNAL_API_KEY}
CENTER = {"q": 0, "r": 0, "s": 0}


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


async def lasting_state(client, room_id, token):
    """The session without the server time, which differs on every call."""
    state = await session(client, room_id, token)
    del state["public"]["server_time"]
    return state


async def stream_tail():
    """The stream ID after which the next room event lands, read like the gateway does."""
    entries = await app.state.redis.redis.xrevrange(EVENTS_STREAM, count=1)
    return entries[0][0] if entries else "0-0"


async def next_event(room_id, after):
    """The raw JSON of the room's first event after the given stream ID."""
    while True:
        reply = await app.state.redis.redis.xread({EVENTS_STREAM: after}, block=2000)
        assert reply, "no event arrived"
        for entry_id, fields in reply[0][1]:
            after = entry_id
            if json.loads(fields["data"])["room_id"] == room_id:
                return fields["data"]


async def started_room(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()
    response = await act(client, host["room_id"], host["token"], "start_game")
    assert response.status_code == 200
    return host, guest


async def edit_game(room_id, change):
    """Puts the stored game in the state a test needs, as a sequence of turns would."""
    redis = app.state.redis
    game = GameSerializer.dict_to_game(await redis.get_game_state(room_id))
    change(game)
    await redis.save_game_state(room_id, GameSerializer.game_to_dict(game))


async def load_game(room_id):
    return GameSerializer.dict_to_game(await app.state.redis.get_game_state(room_id))


SETUP_HEXES = [Hex(-2, 0, 2), Hex(0, 0, 0), Hex(2, 0, -2), Hex(0, -2, 2)]


def past_setup(game):
    """Gives everyone a settlement and a road, then hands the dice to the first player."""
    game.setup_queue = []
    game.setup_waiting_for_road = False
    game.turn_phase = TurnPhase.ROLL_DICE
    for player, h in zip(game.players, SETUP_HEXES[:len(game.players)], strict=True):
        vertex = Vertex(h, 0).get_canonical()
        game.settlements[vertex] = Building(player.color, BuildingType.SETTLEMENT)
        game.roads[vertex.get_touching_edges()[0].get_canonical()] = player.color
        player.victory_points = 1
