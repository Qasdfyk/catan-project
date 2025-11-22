import json
from redis.asyncio import Redis
from app.core.config import settings

class RedisService:
    def __init__(self):
        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def save_game_state(self, room_id: str, game_data: dict, ttl: int = 3600):
        key = f"game:{room_id}"
        await self.redis.set(key, json.dumps(game_data), ex=ttl)

    async def get_game_state(self, room_id: str) -> dict | None:
        key = f"game:{room_id}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def close(self):
        await self.redis.aclose()