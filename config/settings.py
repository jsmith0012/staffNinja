from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    DISCORD_TOKEN: str
    DISCORD_GUILD_ID: str
    DISCORD_CLIENT_SECRET: str | None = None
    DISCORD_INTENTS_MEMBERS: bool = False
    DISCORD_INTENTS_MESSAGE_CONTENT: bool = False
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SSL: str = "prefer"
    AI_PROVIDER: str = "local_stub"
    AI_ENDPOINT: str = "http://localhost:8000/v1"
    LOG_LEVEL: str = "INFO"

def get_settings() -> Settings:
    return Settings()