import os

# Tests create rooms, summon bots and clear the bot stream. On the database of a
# running scripts/dev.sh that would take the seats away from the bots of a game
# being played, so tests get a database of their own (the gateway's use 15).
# Set before app.core.config is imported, which reads it once.
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/14")
