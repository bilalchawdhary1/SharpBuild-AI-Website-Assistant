from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SharpBuild AI Website Assistant"
    database_url: str                      # required: app won't start without it
    gemini_api_key: str = ""               # free key from https://aistudio.google.com/apikey
    embedding_model: str = "gemini-embedding-001"
    generation_model: str = "gemini-2.5-flash"
    allowed_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()