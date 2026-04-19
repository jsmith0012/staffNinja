import pytest
import db.queries

@pytest.mark.asyncio
async def test_check_server_health():
    """Verify that we can run simple queries against the dev DB."""
    healthy = await db.queries.check_server_health()
    assert healthy is True

@pytest.mark.asyncio
async def test_find_user_by_email_for_link():
    """Verify link lookup query doesn't crash on invalid emails."""
    res = await db.queries.find_user_by_email_for_link("nobody@example.com")
    assert isinstance(res, list)

@pytest.mark.asyncio
async def test_is_leadership_user():
    """Verify leadership check runs successfully."""
    res = await db.queries.is_leadership_user(["@nobody"])
    assert isinstance(res, bool)
