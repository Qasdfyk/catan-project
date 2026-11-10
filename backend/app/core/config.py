from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Catan Backend"
    REDIS_URL: str = "redis://localhost:6379/0"
    # Shared with the Go gateway; protects the /internal endpoints
    INTERNAL_API_KEY: str = "dev-internal-key"
    # Room events kept in the stream; a gateway that falls further behind resyncs its clients
    EVENTS_STREAM_MAXLEN: int = 10000
    # Finished games, one gzipped JSON record each (docs/game-record.md)
    RECORDS_DIR: str = "records"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
