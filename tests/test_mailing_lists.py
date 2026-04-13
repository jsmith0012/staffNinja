"""Unit tests for mailing list service and cog helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.google_groups_service import (
    get_allowed_groups,
    get_protected_groups,
    get_leadership_positions,
    get_leadership_protected_groups,
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
@patch("bot.cogs.mailing_lists.Database")
async def test_get_user_email_found(mock_db):
    from bot.cogs.mailing_lists import _get_user_email

    mock_db.fetch = AsyncMock(return_value=[{"email": "staff@example.com"}])
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = "TestUser"
    user.display_name = "TestUser"

    result = await _get_user_email(user)
    assert result == "staff@example.com"
    mock_db.fetch.assert_called_once()


@pytest.mark.asyncio
@patch("bot.cogs.mailing_lists.Database")
async def test_get_user_email_not_linked(mock_db):
    from bot.cogs.mailing_lists import _get_user_email

    mock_db.fetch = AsyncMock(return_value=[])
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = None
    user.display_name = "testuser"

    result = await _get_user_email(user)
    assert result is None


# ---------------------------------------------------------------------------
# Leadership position helpers
# ---------------------------------------------------------------------------

@patch("services.google_groups_service.get_settings")
def test_get_leadership_positions_parses_csv(mock_settings):
    mock_settings.return_value = MagicMock(LEADERSHIP_POSITIONS="Director, Coordinator, Department Head")
    result = get_leadership_positions()
    assert result == {"director", "coordinator", "department head"}


@patch("services.google_groups_service.get_settings")
def test_get_leadership_positions_empty(mock_settings):
    mock_settings.return_value = MagicMock(LEADERSHIP_POSITIONS="")
    assert get_leadership_positions() == set()


@patch("services.google_groups_service.get_settings")
def test_get_leadership_protected_groups_parses_csv(mock_settings):
    mock_settings.return_value = MagicMock(LEADERSHIP_PROTECTED_GROUPS="leaders@example.com, directors@example.com")
    result = get_leadership_protected_groups()
    assert result == {"leaders@example.com", "directors@example.com"}


@patch("services.google_groups_service.get_settings")
def test_get_leadership_protected_groups_empty(mock_settings):
    mock_settings.return_value = MagicMock(LEADERSHIP_PROTECTED_GROUPS="")
    assert get_leadership_protected_groups() == set()


@patch("services.google_groups_service.get_settings")
def test_is_protected_leadership_user(mock_settings):
    """A leadership user cannot opt out of leadership-protected groups."""
    mock_settings.return_value = MagicMock(
        MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com",
        LEADERSHIP_POSITIONS="Director,Coordinator",
        LEADERSHIP_PROTECTED_GROUPS="leaders@example.com",
    )
    # Leadership user trying leadership-protected group
    assert is_protected("leaders@example.com", ["Director"]) is True
    # Regular group is not protected for leadership user
    assert is_protected("social@example.com", ["Director"]) is False
    # Global-protected group is still protected for everyone
    assert is_protected("allstaff@example.com", ["Director"]) is True
    assert is_protected("allstaff@example.com") is True


@patch("services.google_groups_service.get_settings")
def test_is_protected_non_leadership_user(mock_settings):
    """A non-leadership user can opt out of leadership-protected groups."""
    mock_settings.return_value = MagicMock(
        MAILINGLIST_PROTECTED_GROUPS="allstaff@example.com",
        LEADERSHIP_POSITIONS="Director,Coordinator",
        LEADERSHIP_PROTECTED_GROUPS="leaders@example.com",
    )
    # Non-leadership user: leaders group is NOT protected
    assert is_protected("leaders@example.com", ["Volunteer"]) is False
    assert is_protected("leaders@example.com", []) is False
    assert is_protected("leaders@example.com") is False


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
@patch("services.google_groups_service._build_service")
async def test_get_user_groups_leadership_protection(mock_build, mock_settings):
    """Leadership users see leadership-protected groups as protected."""
    mock_settings.return_value = MagicMock(
        MAILINGLIST_GROUPS="news@example.com,leaders@example.com",
        MAILINGLIST_PROTECTED_GROUPS="",
        LEADERSHIP_POSITIONS="Director",
        LEADERSHIP_PROTECTED_GROUPS="leaders@example.com",
    )
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.groups.return_value.list.return_value.execute.return_value = {
        "groups": [
            {"email": "news@example.com", "name": "News", "description": ""},
            {"email": "leaders@example.com", "name": "Leaders", "description": ""},
        ]
    }

    results = await get_user_groups("user@example.com", ["Director"])

    leaders = next(g for g in results if g["email"] == "leaders@example.com")
    assert leaders["is_protected"] is True

    news = next(g for g in results if g["email"] == "news@example.com")
    assert news["is_protected"] is False


@pytest.mark.asyncio
@patch("services.google_groups_service.get_settings")
async def test_remove_member_rejects_leadership_protected(mock_settings):
    """Leadership users cannot unsubscribe from leadership-protected groups."""
    mock_settings.return_value = MagicMock(
        MAILINGLIST_PROTECTED_GROUPS="",
        LEADERSHIP_POSITIONS="Director",
        LEADERSHIP_PROTECTED_GROUPS="leaders@example.com",
    )
    with pytest.raises(GoogleGroupsError, match="protected"):
        await remove_member("leaders@example.com", "user@example.com", ["Director"])


@pytest.mark.asyncio
@patch("bot.cogs.mailing_lists.Database")
async def test_get_user_positions_found(mock_db):
    from bot.cogs.mailing_lists import _get_user_positions

    mock_db.fetch = AsyncMock(return_value=[
        {"position_name": "Director"},
        {"position_name": "Coordinator"},
    ])
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = "TestUser"
    user.display_name = "TestUser"

    result = await _get_user_positions(user)
    assert result == ["Director", "Coordinator"]


@pytest.mark.asyncio
@patch("bot.cogs.mailing_lists.Database")
async def test_get_user_positions_none(mock_db):
    from bot.cogs.mailing_lists import _get_user_positions

    mock_db.fetch = AsyncMock(return_value=[])
    user = MagicMock()
    user.id = 123456789
    user.name = "testuser"
    user.global_name = None
    user.display_name = "testuser"

    result = await _get_user_positions(user)
    assert result == []
