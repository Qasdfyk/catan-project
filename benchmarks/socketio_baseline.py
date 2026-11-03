"""
The fan-out of the gateway written with python-socketio, as the project first
had it: room events arrive from Redis and each member gets its own message.
Run with: pip install python-socketio uvicorn redis
          uvicorn socketio_baseline:app --port 8090
"""
import asyncio
import json
from collections import defaultdict

import socketio
from redis.asyncio import Redis

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
members = defaultdict(set)
background_tasks = set()  # The event loop only keeps weak references to tasks


@sio.on("join")
async def join(sid, room):
    members[room].add(sid)


@sio.on("disconnect")
async def leave(sid):
    for room in members.values():
        room.discard(sid)


async def consume_events():
    pubsub = Redis.from_url("redis://localhost:6380/0", decode_responses=True).pubsub()
    await pubsub.subscribe("catan:events")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        event = json.loads(message["data"])
        for sid in members[event["room_id"]]:
            await sio.emit("state", event["public"], to=sid)


async def asgi_lifespan(scope, receive, send):
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            background_tasks.add(asyncio.create_task(consume_events()))
            await send({"type": "lifespan.startup.complete"})
        else:
            await send({"type": "lifespan.shutdown.complete"})
            return


engine = socketio.ASGIApp(sio)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await asgi_lifespan(scope, receive, send)
    else:
        await engine(scope, receive, send)
