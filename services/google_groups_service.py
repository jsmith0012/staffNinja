import asyncio
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config.settings import get_settings
from utils.errors import GoogleGroupsError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/admin.directory.group.member",
    "https://www.googleapis.com/auth/admin.directory.group.readonly",
]

_service = None


def _build_service():
    """Build and cache the Google Admin SDK Directory service."""
    global _service
    if _service is not None:
        return _service

    settings = get_settings()
    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE:
        raise GoogleGroupsError("GOOGLE_SERVICE_ACCOUNT_FILE is not configured")
    if not settings.GOOGLE_DELEGATED_ADMIN:
        raise GoogleGroupsError("GOOGLE_DELEGATED_ADMIN is not configured")

    credentials = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    delegated = credentials.with_subject(settings.GOOGLE_DELEGATED_ADMIN)
    _service = build("admin", "directory_v1", credentials=delegated)
    return _service


def get_allowed_groups() -> list[str]:
    """Return the list of group emails users are allowed to see/manage."""
    settings = get_settings()
    raw = settings.MAILINGLIST_GROUPS.strip()
    if not raw:
        return []
    return [g.strip().lower() for g in raw.split(",") if g.strip()]


def get_protected_groups() -> set[str]:
    """Return the set of group emails that cannot be opted out of."""
    settings = get_settings()
    raw = settings.MAILINGLIST_PROTECTED_GROUPS.strip()
    if not raw:
        return set()
    return {g.strip().lower() for g in raw.split(",") if g.strip()}


def get_leadership_positions() -> set[str]:
    """Return the set of staff position names considered leadership."""
    settings = get_settings()
    raw = settings.LEADERSHIP_POSITIONS.strip()
    if not raw:
        return set()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def get_leadership_protected_groups() -> set[str]:
    """Return group emails that leadership staff cannot opt out of."""
    settings = get_settings()
    raw = settings.LEADERSHIP_PROTECTED_GROUPS.strip()
    if not raw:
        return set()
    return {g.strip().lower() for g in raw.split(",") if g.strip()}


def is_protected(group_email: str, user_positions: list[str] | None = None) -> bool:
    """Check if a group is protected for the given user.

    A group is protected if it's in the global protected list, or if the user
    holds a leadership position and the group is in the leadership-protected list.
    """
    email = group_email.strip().lower()
    if email in get_protected_groups():
        return True
    if user_positions:
        lp = get_leadership_positions()
        if lp and any(p.lower() in lp for p in user_positions):
            if email in get_leadership_protected_groups():
                return True
    return False


async def get_user_groups(user_email: str, user_positions: list[str] | None = None) -> list[dict]:
    """Return the configured mailing-list groups with membership status for a user.

    Returns a list of dicts: {"email", "name", "description", "is_member", "is_protected"}
    """
    allowed = get_allowed_groups()
    if not allowed:
        return []

    protected = get_protected_groups()
    leadership_protected = set()
    if user_positions:
        lp = get_leadership_positions()
        if lp and any(p.lower() in lp for p in user_positions):
            leadership_protected = get_leadership_protected_groups()

    try:
        service = _build_service()
        response = await asyncio.to_thread(
            service.groups().list(userKey=user_email, maxResults=200).execute,
        )
    except HttpError as exc:
        if exc.resp.status == 404:
            response = {}
        else:
            logger.exception("Google Groups API error for %s", user_email)
            raise GoogleGroupsError(f"Google API error: {exc.resp.status}") from exc
    except Exception as exc:
        logger.exception("Failed to query Google Groups for %s", user_email)
        raise GoogleGroupsError(str(exc)) from exc

    member_groups = {
        g["email"].lower()
        for g in response.get("groups", [])
    }

    # Build a name/description lookup from groups the user is in
    group_info = {
        g["email"].lower(): {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in response.get("groups", [])
    }

    results = []
    for email in allowed:
        info = group_info.get(email, {"name": email.split("@")[0], "description": ""})
        results.append({
            "email": email,
            "name": info["name"] or email.split("@")[0],
            "description": info["description"],
            "is_member": email in member_groups,
            "is_protected": email in protected or email in leadership_protected,
        })
    return results


async def remove_member(group_email: str, user_email: str, user_positions: list[str] | None = None) -> None:
    """Remove a user from a Google Group (opt out)."""
    if is_protected(group_email, user_positions):
        raise GoogleGroupsError(f"Cannot opt out of protected group: {group_email}")

    try:
        service = _build_service()
        await asyncio.to_thread(
            service.members().delete(
                groupKey=group_email, memberKey=user_email,
            ).execute,
        )
        logger.info("Removed %s from group %s", user_email, group_email)
    except HttpError as exc:
        if exc.resp.status == 404:
            logger.warning("User %s not in group %s (already removed)", user_email, group_email)
            return
        logger.exception("Failed to remove %s from %s", user_email, group_email)
        raise GoogleGroupsError(f"Google API error: {exc.resp.status}") from exc


async def add_member(group_email: str, user_email: str) -> None:
    """Add a user to a Google Group (opt in)."""
    try:
        service = _build_service()
        body = {"email": user_email, "role": "MEMBER"}
        await asyncio.to_thread(
            service.members().insert(groupKey=group_email, body=body).execute,
        )
        logger.info("Added %s to group %s", user_email, group_email)
    except HttpError as exc:
        if exc.resp.status == 409:
            logger.warning("User %s already in group %s", user_email, group_email)
            return
        logger.exception("Failed to add %s to %s", user_email, group_email)
        raise GoogleGroupsError(f"Google API error: {exc.resp.status}") from exc
