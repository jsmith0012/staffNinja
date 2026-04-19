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
    EMAIL_SMTP_HOST: str = "smtp.gmail.com"
    EMAIL_SMTP_PORT: int = 465
    EMAIL_SMTP_USERNAME: str | None = None
    EMAIL_SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    LINK_CODE_TTL_MINUTES: int = 10
    LINK_CODE_MAX_ATTEMPTS: int = 5
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SSL: str = "prefer"
    AI_PROVIDER: str = "local_stub"
    AI_ENDPOINT: str = "http://localhost:8000/v1"
    AI_MODEL: str = "qwen2.5:3b"
    AI_REQUEST_TIMEOUT_SECONDS: int = 120
    AI_MAX_CONCURRENT_REQUESTS: int = 2
    LOG_LEVEL: str = "INFO"
    COMMAND_RESYNC_MINUTES: int = 30
    CHAT_MONITOR_ENABLED: bool = True
    CHAT_MONITOR_CHANNELS: str = ""
    CHAT_MONITOR_DOC_CATEGORIES: str = ""
    CHAT_MONITOR_COOLDOWN_SECONDS: int = 30
    CHAT_MONITOR_USER_COOLDOWN_SECONDS: int = 20
    CHAT_MONITOR_MAX_QUESTION_CHARS: int = 600
    JOB_WORKER_POLL_SECONDS: float = 5.0
    JOB_STALE_TIMEOUT_SECONDS: int = 600
    GOOGLE_SERVICE_ACCOUNT_FILE: str | None = None
    GOOGLE_DELEGATED_ADMIN: str | None = None
    MAILINGLIST_GROUPS: str = ""
    MAILINGLIST_PROTECTED_GROUPS: str = ""
    MAILINGLIST_LEADERSHIP_GROUP: str = ""
    DISABLED_COMMANDS: str = ""
    DB_BACKUP_ENABLED: bool = True
    DB_BACKUP_DIR: str = "/home/jsmith/staffNinja/backups"
    DB_BACKUP_HOUR: int = 3

def get_settings() -> Settings:
    return Settings()