"""Unit tests for mailing list service and cog helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.google_groups_service import (
    get_allowed_groups,
    get_protected_groups,
    is_protected,
    get_user_groups,
    remove_member,
    add_member,
)
from utils.errors import GoogleGroupsError


# ---------------------------------------------------------------------------
# Config helper tests
# ---------------------------------------------------------------------------

@patch("services.google_groups_service.get_settings")
def test_get_allowed_groups_parses_csv(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_GROUPS="news@example.com, social@example.com ,  events@example.com")
    result = get_allowed_groups()
    assert result == ["news@example.com", "social@example.com", "events@example.com"]


@patch("services.google_groups_service.get_settings")
def test_get_allowed_groups_empty(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_GROUPS="")
    assert get_allowed_groups() == []


@patch("services.google_groups_service.get_settings")
def test_get_protected_groups_parses_csv(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com")
    result = get_protected_groups()
    assert result == {"allstaff@example.com"}


@patch("services.google_groups_service.get_settings")
def test_get_protected_groups_empty(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="")
    assert get_protected_groups() == set()


@patch("services.google_groups_service.get_settings")
def test_is_protected_true(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com")
    assert is_protected("allstaff@example.com") is True
    assert is_protected("  AllStaff@Example.com  ") is True


@patch("services.google_groups_service.get_settings")
def test_is_protected_false(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com")
    assert is_protected("social@example.com") is False


# ---------------------------------------------------------------------------
# get_user_groups tests (mocked Google API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
@patch("services.google_groups_service._build_service")
async def test_get_user_groups_filters_to_allowed(mock_build, mock_settings):
    mock_settings.return_value = MagicMock(
        MAILINGLIST_GROUPS="news@example.com,social@example.com",
        MAILINGLIST_PROTECTED_GROUPS="news@example.com",
    )

    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.groups.return_value.list.return_value.execute.return_value = {
        "groups": [
            {"email": "news@example.com", "name": "News", "description": "Newsletter"},
            {"email": "social@example.com", "name": "Social", "description": "Social events"},
            {"email": "other@example.com", "name": "Other", "description": "Not configured"},
        ]
    }

    results = await get_user_groups("user@example.com")

    assert len(results) == 2
    news = next(g for g in results if g["email"] == "news@example.com")
    assert news["is_member"] is True
    assert news["is_protected"] is True
    assert news["name"] == "News"

    social = next(g for g in results if g["email"] == "social@example.com")
    assert social["is_member"] is True
    assert social["is_protected"] is False


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
@patch("services.google_groups_service._build_service")
async def test_get_user_groups_shows_unsubscribed(mock_build, mock_settings):
    mock_settings.return_value = MagicMock(
        MAILINGLIST_GROUPS="news@example.com,social@example.com",
        MAILINGLIST_PROTECTED_GROUPS="",
    )

    mock_service = MagicMock()
    mock_build.return_value = mock_service
    # User is only in news, not social
    mock_service.groups.return_value.list.return_value.execute.return_value = {
        "groups": [
            {"email": "news@example.com", "name": "News", "description": ""},
        ]
    }

    results = await get_user_groups("user@example.com")

    assert len(results) == 2
    social = next(g for g in results if g["email"] == "social@example.com")
    assert social["is_member"] is False


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
async def test_get_user_groups_empty_config(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_GROUPS="")
    results = await get_user_groups("user@example.com")
    assert results == []


# ---------------------------------------------------------------------------
# remove_member / add_member tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
@patch("services.google_groups_service._build_service")
async def test_remove_member_calls_api(mock_build, mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="")
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.members.return_value.delete.return_value.execute.return_value = None

    await remove_member("social@example.com", "user@example.com")

    mock_service.members.return_value.delete.assert_called_once_with(
        groupKey="social@example.com", memberKey="user@example.com",
    )


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
async def test_remove_member_rejects_protected(mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com")

    with pytest.raises(GoogleGroupsError, match="protected"):
        await remove_member("allstaff@example.com", "user@example.com")


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
@patch("services.google_groups_service._build_service")
async def test_add_member_calls_api(mock_build, mock_settings):
    mock_settings.return_value = MagicMock(MAILINGLIST_PROTECTED_GROUPS="")
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.members.return_value.insert.return_value.execute.return_value = None

    await add_member("social@example.com", "user@example.com")

    mock_service.members.return_value.insert.assert_called_once_with(
        groupKey="social@example.com",
        body={"email": "user@example.com", "role": "MEMBER"},
    )


# ---------------------------------------------------------------------------
# Cog helper: _get_user_email
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("db.queries.get_user_email_by_discord")
async def test_get_user_email_found(mock_db):
    from bot.cogs.mailing_lists import _get_user_email

    mock_db.return_value = "staff@example.com"
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = "TestUser"
    user.display_name = "TestUser"

    result = await _get_user_email(user)
    assert result == "staff@example.com"
    mock_db.assert_called_once()


@pytest.mark.asyncio
@patch("db.queries.get_user_email_by_discord")
async def test_get_user_email_not_linked(mock_db):
    from bot.cogs.mailing_lists import _get_user_email

    mock_db.return_value = None
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = None
    user.display_name = "testuser"

    result = await _get_user_email(user)
    assert result is None


# ---------------------------------------------------------------------------
# Cog helper: _is_leadership
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("db.queries.is_leadership_user")
async def test_is_leadership_true(mock_db):
    from bot.cogs.mailing_lists import _is_leadership

    mock_db.return_value = True
    user = MagicMock()
    user.id = 123456789
    user.name = "leaderuser"
    user.global_name = "LeaderUser"
    user.display_name = "LeaderUser"

    result = await _is_leadership(user)
    assert result is True
    mock_db.assert_called_once()


@pytest.mark.asyncio
@patch("db.queries.is_leadership_user")
async def test_is_leadership_false(mock_db):
    from bot.cogs.mailing_lists import _is_leadership

    mock_db.return_value = False
    user = MagicMock()
    user.id = 123456789
    user.name = "regularuser"
    user.global_name = "RegularUser"
    user.display_name = "RegularUser"

    result = await _is_leadership(user)
    assert result is False


@pytest.mark.asyncio
@patch("db.queries.is_leadership_user")
async def test_is_leadership_no_record(mock_db):
    from bot.cogs.mailing_lists import _is_leadership

    mock_db.return_value = False
    user = MagicMock()
    user.id = 999999999
    user.name = "unknown"
    user.global_name = None
    user.display_name = "unknown"

    result = await _is_leadership(user)
    assert result is False
