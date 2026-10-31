from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Catan Backend"
    REDIS_URL: str = "redis://localhost:6379/0"
    # Shared with the Go gateway; protects the /internal endpoints
    INTERNAL_API_KEY: str = "dev-internal-key"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
