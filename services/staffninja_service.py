import logging
import asyncio
import secrets
import socket
from datetime import datetime, timezone
import smtplib
from email.message import EmailMessage

import db.queries
from config.settings import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

async def get_server_status_text(latency_ms: int, launch_time: datetime) -> str:
    db_status = "unknown"
    db_latency_ms = "n/a"

    try:
        start = datetime.now(timezone.utc)
        ok = await db.queries.check_server_health()
        end = datetime.now(timezone.utc)
        db_status = "ok" if ok else "unexpected response"
        db_latency_ms = str(int((end - start).total_seconds() * 1000))
    except Exception as exc:
        db_status = f"error: {exc.__class__.__name__}"

    uptime = datetime.now(timezone.utc) - launch_time

    lines = [
        "staffNinja server status",
        "- service: running (process online)",
        f"- discord gateway: connected ({latency_ms} ms)",
        f"- database: {db_status} ({db_latency_ms} ms)",
        f"- host: {socket.gethostname()}",
        f"- uptime: {str(uptime).split('.')[0]}",
        f"- checked at: {datetime.now(timezone.utc).isoformat()}",
    ]
    return "\n".join(lines)

def _format_event_timestamp(value):
    if value is None:
        return "(none)"
    try:
        timestamp = int(value)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(value)

def _format_db_timestamp(value):
    if value is None:
        return "(none)"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return str(value)

async def get_formatted_event_status() -> str:
    status_map = {0: "inactive", 1: "active"}
    
    try:
        event = await db.queries.get_active_event_metadata()
    except Exception as exc:
        logger.exception("Failed event lookup")
        return f"Event lookup failed: {exc.__class__.__name__}"

    if not event:
        return "No active event found (Status = 1)."

    selected_event_id = event["Id"]

    try:
        metric = await db.queries.get_event_metrics(selected_event_id)
        venue_name = await db.queries.get_event_venue_name(event["VenueId"]) or "(none)"
    except Exception as exc:
        logger.exception("Failed event metrics lookup event_id=%s", selected_event_id)
        return f"Event metrics lookup failed: {exc.__class__.__name__}"

    status_code = int(event["Status"]) if event["Status"] is not None else -1
    status_label = status_map.get(status_code, f"unknown ({status_code})")

    lines = [
        "staffNinja event status",
        f"- event id: {selected_event_id}",
        f"- name: {event['Name']}",
        f"- status: {status_label}",
        f"- start: {_format_event_timestamp(event['Start'])}",
        f"- end: {_format_event_timestamp(event['End'])}",
        f"- eventbrite id: {event['EventBriteId'] if event['EventBriteId'] else '(none)'}",
        f"- venue: {venue_name}",
        f"- staff agreement form id: {event['StaffAgreementFormId'] if event['StaffAgreementFormId'] else '(none)'}",
        "- related table metrics:",
        f"  attendee badges={metric['attendee_badges']}, budgets={metric['budgets']}, panels={metric['panels']}, staff shifts={metric['staff_shifts']}",
        f"  user prefs={metric['user_preferences']}, transactions={metric['transactions']}, schedules={metric['schedules']}",
        f"  expense budgets={metric['expense_budgets']}, legacy badges={metric['legacy_badges']}, staff events={metric['staff_events']}",
        f"  volunteer awards={metric['volunteer_awards']}, volunteer hours={metric['volunteer_hours']}, volunteer rewards={metric['volunteer_rewards']}",
    ]
    return "\n".join(lines)

def _send_verification_email(recipient_email: str, code: str):
    if not settings.EMAIL_SMTP_USERNAME or not settings.EMAIL_SMTP_PASSWORD or not settings.EMAIL_FROM:
        raise RuntimeError("Email delivery is not configured")

    msg = EmailMessage()
    msg["Subject"] = "staffNinja account link verification"
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = recipient_email
    msg.set_content(
        "Use this verification code in Discord to link your account:\n\n"
        f"{code}\n\n"
        f"This code expires in {settings.LINK_CODE_TTL_MINUTES} minutes."
    )

    with smtplib.SMTP_SSL(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, timeout=15) as smtp:
        smtp.login(settings.EMAIL_SMTP_USERNAME, settings.EMAIL_SMTP_PASSWORD)
        smtp.send_message(msg)

async def init_link_process(email: str, requestor_id: str) -> dict:
    normalized_email = (email or "").strip().lower()
    if not normalized_email or "@" not in normalized_email:
        return {"success": False, "message": "Please provide a valid email address."}

    try:
        matches = await db.queries.find_user_by_email_for_link(normalized_email)
    except Exception as exc:
        logger.exception("Failed email lookup for link command")
        return {"success": False, "message": f"Account lookup failed: {exc.__class__.__name__}"}

    if not matches:
        return {"success": False, "message": "No matching account could be verified for that email."}

    if len(matches) > 1:
        return {"success": False, "message": "Multiple accounts matched that email. Please contact an admin."}

    row = matches[0]
    existing_discord = (row["discord_value"] or "").strip()

    if existing_discord:
        normalized_existing = existing_discord.lstrip("@").lower()
        if normalized_existing == requestor_id.lower():
            return {"success": False, "message": "Your Discord account is already linked."}
        return {"success": False, "message": "This account is already linked to a Discord identity. Please contact an admin to re-link."}

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc).timestamp() + (settings.LINK_CODE_TTL_MINUTES * 60)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_verification_email, normalized_email, code)
    except Exception as exc:
        logger.exception("Failed to send link verification email")
        return {"success": False, "message": f"Could not send verification email: {exc.__class__.__name__}"}

    return {
        "success": True,
        "message": "Verification code sent. Run `/staffninja verify code:<123456>` to complete linking.",
        "pending_data": {
            "code": code,
            "email": normalized_email,
            "user_id": int(row["Id"]),
            "expires_at": expires_at,
            "attempts": 0,
        }
    }

async def verify_link_code(code: str, requestor_id: str, pending: dict) -> dict:
    if datetime.now(timezone.utc).timestamp() > pending["expires_at"]:
        return {"success": False, "message": "Verification code expired. Run `/staffninja link` again.", "remove_pending": True}

    submitted = (code or "").strip()
    if submitted != pending["code"]:
        pending["attempts"] += 1
        remaining = settings.LINK_CODE_MAX_ATTEMPTS - pending["attempts"]
        if remaining <= 0:
            return {"success": False, "message": "Too many invalid attempts. Run `/staffninja link` again.", "remove_pending": True}
        return {"success": False, "message": f"Invalid code. {remaining} attempts remaining.", "remove_pending": False}

    try:
        result = await db.queries.update_user_discord_link(requestor_id, pending["user_id"])
    except Exception as exc:
        logger.exception("Failed to update Discord link")
        return {"success": False, "message": f"Could not update your profile: {exc.__class__.__name__}", "remove_pending": False}

    if result != "UPDATE 1":
        return {"success": False, "message": "Could not complete link because the account was updated. Please contact an admin.", "remove_pending": True}

    return {"success": True, "message": "Your Discord account has been linked successfully. You can now run `/staffninja status`.", "remove_pending": True}

async def get_formatted_staff_profile(discord_user) -> str:
    handle_candidates = {
        str(discord_user.id).strip().lower(),
        str(discord_user.name).strip().lower(),
        str(getattr(discord_user, "global_name", "") or "").strip().lower(),
        str(getattr(discord_user, "display_name", "") or "").strip().lower(),
    }
    handle_candidates = {h.lstrip("@") for h in handle_candidates if h}

    try:
        row = await db.queries.get_user_staff_profile(list(handle_candidates))
    except Exception as exc:
        logger.exception("Failed staff lookup")
        return f"Staff lookup failed: {exc.__class__.__name__}"

    if not row:
        return "No staff record matched your Discord identity. Run `/staffninja link email:<you@example.com>` to link your account."

    status_map = {0: "inactive", 1: "active", 2: "pending"}
    status_code = int(row["status_code"]) if row["status_code"] is not None else -1
    status_label = status_map.get(status_code, f"unknown ({status_code})")

    full_name = f"{row['first_name']} {row['last_name']}".strip() or "(no name set)"
    email = row["email"] or "(none)"
    preferred_full_name = f"{row['preferred_first_name']} {row['preferred_last_name']}".strip() or "(none)"
    phone = row["phone"] or "(none)"
    birth_date = str(row["birth_date"]) if row["birth_date"] else "(none)"
    allergies = row["allergies"] or "(none)"
    year_joined = str(row["year_joined"]) if row["year_joined"] is not None else "(none)"

    try:
        agreement = await db.queries.get_user_staff_agreements(row["user_id"])
    except Exception as exc:
        logger.exception("Failed staff agreement lookup")
        return f"Staff agreement lookup failed: {exc.__class__.__name__}"

    if not agreement:
        staff_agreement_status = "no active event found"
    else:
        event_name = agreement["event_name"] or f"event {agreement['event_id']}"
        form_id = agreement["staff_agreement_form_id"]
        form_title = agreement["staff_agreement_form_title"] or "staff agreement"
        completed_form_id = agreement["completed_form_id"]

        if not form_id:
            staff_agreement_status = f"not configured for {event_name}"
        elif completed_form_id:
            completed_at = _format_db_timestamp(agreement["completed_at"])
            staff_agreement_status = f"agreed for {event_name} ({form_title}) on {completed_at}"
        else:
            staff_agreement_status = f"not yet agreed for {event_name} ({form_title})"

    lines = [
        "staffNinja staff profile",
        f"- user id: {row['user_id']}",
        f"- name: {full_name}",
        f"- preferred name: {preferred_full_name}",
        f"- discord mapping: {row['discord_value'] or '(none)'}",
        f"- status: {status_label}",
        f"- leadership: {'yes' if row['is_leadership'] else 'no'}",
        f"- staff positions: {row['staff_positions']}",
        f"- email: {email}",
        f"- phone: {phone}",
        f"- birth day: {birth_date}",
        f"- alergys: {allergies}",
        f"- year joined: {year_joined}",
        f"- staff agreement: {staff_agreement_status}",
    ]
    return "\n".join(lines)
