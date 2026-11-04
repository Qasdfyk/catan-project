"""Requests the gateway and the browser make, shared by the integration tests."""
from app.core.config import settings

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


async def started_room(client):
    host = await create_room(client)
    guest = (await join(client, host["room_id"], "Bob")).json()
    response = await act(client, host["room_id"], host["token"], "start_game")
    assert response.status_code == 200
    return host, guest
