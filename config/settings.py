import os
from pydantic import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    DISCORD_TOKEN: str
    DISCORD_GUILD_ID: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    AI_PROVIDER: str = "local_stub"
    AI_ENDPOINT: str = "http://localhost:8000/v1"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

def get_settings() -> Settings:
    return Settings()