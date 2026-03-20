# Contract test for DB integration
# TODO: Implement tests that verify queries against the real schema (read-only)

import pytest
import asyncio
from db.connection import Database

@pytest.mark.asyncio
async def test_db_connection():
    await Database.connect()
    result = await Database.fetch("SELECT 1;")
    assert result[0][0] == 1
    await Database.close()
