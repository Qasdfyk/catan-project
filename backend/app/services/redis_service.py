import json
from redis.asyncio import Redis
from redis.asyncio.lock import Lock
from app.core.config import settings

EVENTS_CHANNEL = "catan:events"
BOTS_CHANNEL = "catan:bots"
ACTIVE_BOTS_KEY = "catan:active_bots"
TURN_DEADLINES_KEY = "catan:turn_deadlines"
ROOM_TTL_SECONDS = 24 * 3600

class RedisService:
    def __init__(self):
        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def save_game_state(self, room_id: str, game_data: dict, ttl: int = ROOM_TTL_SECONDS):
        key = f"game:{room_id}"
        await self.redis.set(key, json.dumps(game_data), ex=ttl)

    async def get_game_state(self, room_id: str) -> dict | None:
        key = f"game:{room_id}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def save_room(self, room_id: str, room: dict, ttl: int = ROOM_TTL_SECONDS):
        await self.redis.set(f"room:{room_id}", json.dumps(room), ex=ttl)

    async def get_room(self, room_id: str) -> dict | None:
        data = await self.redis.get(f"room:{room_id}")
        return json.loads(data) if data else None

    def room_lock(self, room_id: str) -> Lock:
        """Serializes changes to a room across all backend workers."""
        return self.redis.lock(f"lock:{room_id}", timeout=10, blocking_timeout=5)

    async def online_seats(self, room_id: str, seat_count: int) -> set[int]:
        """Presence keys are maintained by the gateway."""
        if seat_count == 0:
            return set()
        keys = [f"presence:{room_id}:{seat}" for seat in range(seat_count)]
        values = await self.redis.mget(keys)
        return {seat for seat, value in enumerate(values) if value is not None}

    async def publish_event(self, event: dict):
        await self.redis.publish(EVENTS_CHANNEL, json.dumps(event))

    async def summon_bot(self, room_id: str, token: str, level: str):
        """Asks the bot service to take a seat. The set lets it recover after a restart."""
        bot = json.dumps({"room_id": room_id, "token": token, "level": level})
        await self.redis.sadd(ACTIVE_BOTS_KEY, bot)
        await self.redis.publish(BOTS_CHANNEL, bot)

    async def set_turn_deadline(self, room_id: str, deadline: float):
        """The bot service polls this set and reports each room whose time is up."""
        await self.redis.zadd(TURN_DEADLINES_KEY, {room_id: deadline})

    async def clear_turn_deadline(self, room_id: str):
        await self.redis.zrem(TURN_DEADLINES_KEY, room_id)

    async def close(self):
        await self.redis.aclose()
