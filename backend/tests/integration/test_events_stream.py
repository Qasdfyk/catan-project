import json
import uuid

import pytest

from app.core.config import settings
from app.services import redis_service
from app.services.redis_service import RedisService


@pytest.fixture
def stream(monkeypatch):
    """A stream of its own, so trimming it cannot touch events a running gateway reads."""
    key = f"test:events:{uuid.uuid4()}"
    monkeypatch.setattr(redis_service, "EVENTS_STREAM", key)
    return key


@pytest.mark.asyncio
async def test_events_are_appended_in_order(stream):
    service = RedisService()

    for version in range(3):
        await service.publish_event({"room_id": "room", "version": version})

    entries = await service.redis.xrange(stream)
    await service.redis.delete(stream)
    await service.close()
    assert [json.loads(fields["data"])["version"] for _, fields in entries] == [0, 1, 2]


@pytest.mark.asyncio
async def test_stream_keeps_about_the_configured_length(stream, monkeypatch):
    monkeypatch.setattr(settings, "EVENTS_STREAM_MAXLEN", 50)
    service = RedisService()

    for version in range(1000):
        await service.publish_event({"room_id": "room", "version": version})

    length = await service.redis.xlen(stream)
    newest = await service.redis.xrevrange(stream, count=1)
    await service.redis.delete(stream)
    await service.close()
    # Approximate trimming drops whole nodes of the stream, so a little more may stay
    assert 50 <= length < 300
    assert json.loads(newest[0][1]["data"])["version"] == 999
