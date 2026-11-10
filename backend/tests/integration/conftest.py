import httpx
import pytest_asyncio

from app.main import app
from app.services.record_store import RecordStore
from app.services.redis_service import RedisService
from app.services.room_service import RoomService


@pytest_asyncio.fixture
async def client(tmp_path):
    # httpx does not run the lifespan, so the app state is set up here
    app.state.redis = RedisService()
    app.state.rooms = RoomService(app.state.redis, RecordStore(tmp_path / "records"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await app.state.redis.close()
