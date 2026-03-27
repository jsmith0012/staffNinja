import asyncpg
import logging
from config.settings import get_settings

class Database:
    _pool = None

    @classmethod
    async def connect(cls):
        settings = get_settings()
        try:
            ssl_mode = settings.POSTGRES_SSL.strip().lower()
            ssl_value = None if ssl_mode in {"", "disable", "false", "0"} else ssl_mode
            cls._pool = await asyncpg.create_pool(
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                database=settings.POSTGRES_DB,
                ssl=ssl_value,
                min_size=1,
                max_size=5,
            )
            logging.info("Database pool created.")
        except Exception as e:
            logging.error(f"Failed to connect to DB: {e}")
            raise

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            logging.info("Database pool closed.")

    @classmethod
    async def fetch(cls, query, *args):
        if not cls._pool:
            await cls.connect()
        async with cls._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def execute(cls, query, *args):
        if not cls._pool:
            await cls.connect()
        async with cls._pool.acquire() as conn:
            return await conn.execute(query, *args)
