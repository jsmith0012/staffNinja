import os
import pytest
from db.connection import Database

os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"
os.environ["POSTGRES_DB"] = "staffninja_dev"
os.environ["POSTGRES_USER"] = "staffninja_dev"
os.environ["POSTGRES_PASSWORD"] = "change-me"
os.environ["POSTGRES_SSL"] = "disable"

@pytest.fixture(autouse=True)
async def reset_db_pool():
    Database._pool = None
    yield
    if Database._pool:
        try:
            await Database.close()
        except Exception:
            pass
