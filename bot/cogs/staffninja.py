import asyncio
import re
import socket
from datetime import datetime, timezone
import logging
import secrets
import smtplib
from email.message import EmailMessage

import discord
from discord import app_commands
from discord.ext import commands

from ai.provider import get_provider
from config.settings import get_settings
from db.connection import Database

settings = get_settings()


class StaffNinjaGroup(app_commands.Group):
    pending_link_challenges: dict[int, dict] = {}

    def __init__(self):
        super().__init__(name="staffninja", description="staffNinja bot commands")

    @staticmethod
    def _format_event_timestamp(value):
        if value is None:
            return "(none)"

        try:
            timestamp = int(value)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return str(value)

    @staticmethod
    def _format_db_timestamp(value):
        if value is None:
            return "(none)"

        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        return str(value)

    @staticmethod
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

    @app_commands.command(name="server", description="Show private bot/server health status")
    async def server(self, interaction: discord.Interaction):
        db_status = "unknown"
        db_latency_ms = "n/a"

        try:
            start = datetime.now(timezone.utc)
            rows = await Database.fetch("SELECT 1 AS ok")
            end = datetime.now(timezone.utc)
            ok = rows and rows[0]["ok"] == 1
            db_status = "ok" if ok else "unexpected response"
            db_latency_ms = str(int((end - start).total_seconds() * 1000))
        except Exception as exc:
            db_status = f"error: {exc.__class__.__name__}"

        latency_ms = int((interaction.client.latency or 0) * 1000)
        uptime = datetime.now(timezone.utc) - interaction.client.launch_time

        lines = [
            "staffNinja server status",
            f"- service: running (process online)",
            f"- discord gateway: connected ({latency_ms} ms)",
            f"- database: {db_status} ({db_latency_ms} ms)",
            f"- host: {socket.gethostname()}",
            f"- uptime: {str(uptime).split('.')[0]}",
            f"- checked at: {datetime.now(timezone.utc).isoformat()}",
        ]

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="help", description="Show available slash commands")
    async def help(self, interaction: discord.Interaction):
        lines = [
            "staffNinja slash command help",
            "- /staffninja server: private health report for bot/server/db status",
            "- /staffninja help: this command list",
            "- /staffninja status: your staff profile/status from the User table",
            "- /staffninja event: active event status and related metrics",
            "- /eventninja policy <question>: answers from Document table excerpts only",
            "- /staffninja link email:<you@example.com>: sends a verification code to your email",
            "- /staffninja verify code:<123456>: verifies code and links your Discord account",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="event", description="Show event status and related metrics")
    async def event(self, interaction: discord.Interaction):
        status_map = {
            0: "inactive",
            1: "active",
        }

        try:
            event_rows = await Database.fetch(
                'SELECT "Id", "Name", "Status", "Start", "End", "EventBriteId", "VenueId", "StaffAgreementFormId" FROM "Event" WHERE "Status" = 1 ORDER BY "Id" DESC LIMIT 1'
            )
        except Exception as exc:
            logging.exception("Failed event lookup")
            await interaction.response.send_message(
                f"Event lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not event_rows:
            await interaction.response.send_message(
                "No active event found (Status = 1).",
                ephemeral=True,
            )
            return

        event = event_rows[0]
        selected_event_id = event["Id"]

        try:
            metrics = await Database.fetch(
                """
                SELECT
                    (SELECT COUNT(*) FROM "AttendeeBadge" WHERE "EventId" = $1) AS attendee_badges,
                    (SELECT COUNT(*) FROM "Budget" WHERE "EventId" = $1) AS budgets,
                    (SELECT COUNT(*) FROM "Panel" WHERE "EventId" = $1) AS panels,
                    (SELECT COUNT(*) FROM "StaffShift" WHERE "EventId" = $1) AS staff_shifts,
                    (SELECT COUNT(*) FROM "UserEventPreferences" WHERE "EventId" = $1) AS user_preferences,
                    (SELECT COUNT(*) FROM "Transaction" WHERE "EventId" = $1) AS transactions,
                    (SELECT COUNT(*) FROM "conExpenseBudget" WHERE "sysEventId" = $1) AS expense_budgets,
                    (SELECT COUNT(*) FROM "deprecated_regBadge" WHERE "eventId" = $1) AS legacy_badges,
                    (SELECT COUNT(*) FROM "schSchedule" WHERE "sysEventId" = $1) AS schedules,
                    (SELECT COUNT(*) FROM "stfEvent" WHERE "eventId" = $1) AS staff_events,
                    (SELECT COUNT(*) FROM "volAwarded" WHERE "eventId" = $1) AS volunteer_awards,
                    (SELECT COUNT(*) FROM "volHours" WHERE "eventId" = $1) AS volunteer_hours,
                    (SELECT COUNT(*) FROM "volRewards" WHERE "eventId" = $1) AS volunteer_rewards
                """,
                selected_event_id,
            )
            venue = await Database.fetch(
                'SELECT COALESCE("Name", \'(none)\') AS venue_name FROM "Venue" WHERE "Id" = $1 LIMIT 1',
                event["VenueId"],
            )
        except Exception as exc:
            logging.exception("Failed event metrics lookup event_id=%s", selected_event_id)
            await interaction.response.send_message(
                f"Event metrics lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        metric = metrics[0]
        venue_name = venue[0]["venue_name"] if venue else "(none)"
        status_code = int(event["Status"]) if event["Status"] is not None else -1
        status_label = status_map.get(status_code, f"unknown ({status_code})")

        lines = [
            "staffNinja event status",
            f"- event id: {selected_event_id}",
            f"- name: {event['Name']}",
            f"- status: {status_label}",
            f"- start: {self._format_event_timestamp(event['Start'])}",
            f"- end: {self._format_event_timestamp(event['End'])}",
            f"- eventbrite id: {event['EventBriteId'] if event['EventBriteId'] else '(none)'}",
            f"- venue: {venue_name}",
            f"- staff agreement form id: {event['StaffAgreementFormId'] if event['StaffAgreementFormId'] else '(none)'}",
            "- related table metrics:",
            f"  attendee badges={metric['attendee_badges']}, budgets={metric['budgets']}, panels={metric['panels']}, staff shifts={metric['staff_shifts']}",
            f"  user prefs={metric['user_preferences']}, transactions={metric['transactions']}, schedules={metric['schedules']}",
            f"  expense budgets={metric['expense_budgets']}, legacy badges={metric['legacy_badges']}, staff events={metric['staff_events']}",
            f"  volunteer awards={metric['volunteer_awards']}, volunteer hours={metric['volunteer_hours']}, volunteer rewards={metric['volunteer_rewards']}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="link", description="Link your Discord account to your staff record by email")
    @app_commands.describe(email="Email address on your staff record")
    async def link(self, interaction: discord.Interaction, email: str):
        normalized_email = (email or "").strip().lower()
        if not normalized_email or "@" not in normalized_email:
            await interaction.response.send_message(
                "Please provide a valid email address.",
                ephemeral=True,
            )
            return

        # Defer immediately before any I/O — DB lookup + SMTP can exceed Discord's 3s window
        await interaction.response.defer(ephemeral=True)

        try:
            matches = await Database.fetch(
                'SELECT "Id", COALESCE("Discord", \'\') AS discord_value FROM "User" WHERE LOWER(COALESCE("Email", \'\')) = $1',
                normalized_email,
            )
        except Exception as exc:
            logging.exception("Failed email lookup for link command user_id=%s", getattr(interaction.user, "id", None))
            await interaction.followup.send(
                f"Account lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not matches:
            await interaction.followup.send(
                "No matching account could be verified for that email.",
                ephemeral=True,
            )
            return

        if len(matches) > 1:
            await interaction.followup.send(
                "Multiple accounts matched that email. Please contact an admin.",
                ephemeral=True,
            )
            return

        row = matches[0]
        existing_discord = (row["discord_value"] or "").strip()
        requestor_id = str(interaction.user.id)

        if existing_discord:
            normalized_existing = existing_discord.lstrip("@").lower()
            if normalized_existing == requestor_id.lower():
                await interaction.followup.send(
                    "Your Discord account is already linked.",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                "This account is already linked to a Discord identity. Please contact an admin to re-link.",
                ephemeral=True,
            )
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc).timestamp() + (settings.LINK_CODE_TTL_MINUTES * 60)

        try:
            # Run blocking SMTP call in a thread so it doesn't stall the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_verification_email, normalized_email, code)
        except Exception as exc:
            logging.exception("Failed to send link verification email user_id=%s", getattr(interaction.user, "id", None))
            await interaction.followup.send(
                f"Could not send verification email: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        self.pending_link_challenges[int(interaction.user.id)] = {
            "code": code,
            "email": normalized_email,
            "user_id": int(row["Id"]),
            "expires_at": expires_at,
            "attempts": 0,
        }

        await interaction.followup.send(
            "Verification code sent. Run `/staffninja verify code:<123456>` to complete linking.",
            ephemeral=True,
        )

    @app_commands.command(name="verify", description="Verify your email code and complete account linking")
    @app_commands.describe(code="6-digit code sent to your email")
    async def verify(self, interaction: discord.Interaction, code: str):
        user_id = int(interaction.user.id)
        requestor_id = str(interaction.user.id)
        pending = self.pending_link_challenges.get(user_id)

        if not pending:
            await interaction.response.send_message(
                "No pending link request found. Run `/staffninja link` first.",
                ephemeral=True,
            )
            return

        if datetime.now(timezone.utc).timestamp() > pending["expires_at"]:
            self.pending_link_challenges.pop(user_id, None)
            await interaction.response.send_message(
                "Verification code expired. Run `/staffninja link` again.",
                ephemeral=True,
            )
            return

        submitted = (code or "").strip()
        if submitted != pending["code"]:
            pending["attempts"] += 1
            remaining = settings.LINK_CODE_MAX_ATTEMPTS - pending["attempts"]
            if remaining <= 0:
                self.pending_link_challenges.pop(user_id, None)
                await interaction.response.send_message(
                    "Too many invalid attempts. Run `/staffninja link` again.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"Invalid code. {remaining} attempts remaining.",
                ephemeral=True,
            )
            return

        try:
            result = await Database.execute(
                'UPDATE "User" SET "Discord" = $1 WHERE "Id" = $2 AND COALESCE("Discord", \'\') = \'\'',
                requestor_id,
                pending["user_id"],
            )
        except Exception as exc:
            logging.exception("Failed to update Discord link for user_id=%s", getattr(interaction.user, "id", None))
            await interaction.response.send_message(
                f"Could not update your profile: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if result != "UPDATE 1":
            self.pending_link_challenges.pop(user_id, None)
            await interaction.response.send_message(
                "Could not complete link because the account was updated. Please contact an admin.",
                ephemeral=True,
            )
            return

        self.pending_link_challenges.pop(user_id, None)

        await interaction.response.send_message(
            "Your Discord account has been linked successfully. You can now run `/staffninja staff`.",
            ephemeral=True,
        )

    @app_commands.command(name="status", description="Show your staff profile and status")
    async def staff(self, interaction: discord.Interaction):
        user = interaction.user
        handle_candidates = {
            str(user.id).strip().lower(),
            str(user.name).strip().lower(),
            str(getattr(user, "global_name", "") or "").strip().lower(),
            str(getattr(user, "display_name", "") or "").strip().lower(),
        }
        handle_candidates = {h.lstrip("@") for h in handle_candidates if h}

        query = """
            SELECT
                u."Id" AS user_id,
                COALESCE(u."FirstName", '') AS first_name,
                COALESCE(u."LastName", '') AS last_name,
                COALESCE(u."PreferredFirstName", '') AS preferred_first_name,
                COALESCE(u."PreferredLastName", '') AS preferred_last_name,
                COALESCE(u."Discord", '') AS discord_value,
                u."Email" AS email,
                u."Phone" AS phone,
                u."BirthDate" AS birth_date,
                u."Allergy" AS allergies,
                u."YearJoined" AS year_joined,
                u."Status" AS status_code,
                COALESCE(string_agg(DISTINCT sp."Name", ', '), 'None') AS staff_positions
            FROM "User" u
            LEFT JOIN "UserStaffPosition" usp ON usp."UserId" = u."Id"
            LEFT JOIN "StaffPosition" sp ON sp."Id" = usp."StaffPositionId"
            WHERE LOWER(TRIM(BOTH '@' FROM COALESCE(u."Discord", ''))) = ANY($1::text[])
            GROUP BY u."Id", u."FirstName", u."LastName", u."PreferredFirstName", u."PreferredLastName", u."Discord", u."Email", u."Phone", u."BirthDate", u."Allergy", u."YearJoined", u."Status"
            ORDER BY u."Id"
            LIMIT 1
        """

        try:
            rows = await Database.fetch(query, list(handle_candidates))
        except Exception as exc:
            logging.exception("Failed staff lookup for user_id=%s", getattr(user, "id", None))
            await interaction.response.send_message(
                f"Staff lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not rows:
            await interaction.response.send_message(
                "No staff record matched your Discord identity. Run `/staffninja link email:<you@example.com>` to link your account.",
                ephemeral=True,
            )
            return

        row = rows[0]
        status_map = {
            0: "inactive",
            1: "active",
            2: "pending",
        }
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
            agreement_rows = await Database.fetch(
                """
                SELECT
                    e."Id" AS event_id,
                    COALESCE(e."Name", '') AS event_name,
                    e."StaffAgreementFormId" AS staff_agreement_form_id,
                    COALESCE(f."Title", '') AS staff_agreement_form_title,
                    cf."Id" AS completed_form_id,
                    COALESCE(cf."EditedDate", cf."CreatedDate") AS completed_at
                FROM "Event" e
                LEFT JOIN "Form" f ON f."Id" = e."StaffAgreementFormId"
                LEFT JOIN LATERAL (
                    SELECT "Id", "EditedDate", "CreatedDate"
                    FROM "CompletedForm"
                    WHERE "FormId" = e."StaffAgreementFormId"
                      AND "UserId" = $1
                    ORDER BY COALESCE("EditedDate", "CreatedDate") DESC NULLS LAST, "Id" DESC
                    LIMIT 1
                ) cf ON TRUE
                WHERE e."Status" = 1
                ORDER BY e."Id" DESC
                LIMIT 1
                """,
                row["user_id"],
            )
        except Exception as exc:
            logging.exception("Failed staff agreement lookup for user_id=%s", row["user_id"])
            await interaction.response.send_message(
                f"Staff agreement lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not agreement_rows:
            staff_agreement_status = "no active event found"
        else:
            agreement = agreement_rows[0]
            event_name = agreement["event_name"] or f"event {agreement['event_id']}"
            form_id = agreement["staff_agreement_form_id"]
            form_title = agreement["staff_agreement_form_title"] or "staff agreement"
            completed_form_id = agreement["completed_form_id"]

            if not form_id:
                staff_agreement_status = f"not configured for {event_name}"
            elif completed_form_id:
                completed_at = self._format_db_timestamp(agreement["completed_at"])
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
            f"- staff positions: {row['staff_positions']}",
            f"- email: {email}",
            f"- phone: {phone}",
            f"- birth day: {birth_date}",
            f"- alergys: {allergies}",
            f"- year joined: {year_joined}",
            f"- staff agreement: {staff_agreement_status}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class EventNinjaGroup(app_commands.Group):
    POLICY_URL_PREFIX = "https://staff.animenebraskon.com/staff/policy/"
    POLICY_DEEP_ANALYZE_LIMIT = 40
    POLICY_CONTEXT_LIMIT = 16

    def __init__(self):
        super().__init__(name="eventninja", description="Event policy commands")

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    @staticmethod
    def _extract_relevant_section(text: str, terms: list[str], section_size: int = 700) -> str:
        if not text:
            return ""

        compact = str(text).replace("\r", "")
        lowered = compact.lower()
        match_positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]

        if not match_positions:
            return compact[:section_size]

        first_match = min(match_positions)
        start = max(0, first_match - (section_size // 3))
        end = min(len(compact), start + section_size)
        return compact[start:end]

    @staticmethod
    def _extract_relevant_sections(text: str, terms: list[str], section_size: int = 420, max_sections: int = 2) -> str:
        if not text:
            return ""

        compact = str(text).replace("\r", "")
        lowered = compact.lower()

        positions: list[int] = []
        for term in terms:
            t = (term or "").strip().lower()
            if not t:
                continue
            idx = lowered.find(t)
            if idx >= 0:
                positions.append(idx)

        if not positions:
            return compact[:section_size]

        positions.sort()
        chosen: list[int] = []
        for pos in positions:
            if not chosen or abs(pos - chosen[-1]) > (section_size // 2):
                chosen.append(pos)
            if len(chosen) >= max_sections:
                break

        snippets: list[str] = []
        for pos in chosen:
            start = max(0, pos - (section_size // 3))
            end = min(len(compact), start + section_size)
            snippets.append(compact[start:end].strip())

        return "\n...\n".join(s for s in snippets if s)

    @staticmethod
    def _extract_query_terms(question: str) -> list[str]:
        cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in (question or "").lower())
        raw_tokens = [t.strip() for t in cleaned.split() if t.strip()]

        # Keep short all-letter acronyms (e.g., "av", "hr") while filtering noisy tiny tokens.
        tokens: list[str] = []
        for token in raw_tokens:
            if len(token) >= 3:
                tokens.append(token)
            elif len(token) == 2 and token.isalpha():
                tokens.append(token)

        seen = set()
        ordered: list[str] = []
        for token in tokens:
            if token not in seen:
                seen.add(token)
                ordered.append(token)
        return ordered

    @staticmethod
    def _build_policy_search_query(question: str) -> str:
        tokens = EventNinjaGroup._extract_query_terms(question)

        expanded_terms = set(tokens)
        if any(t in expanded_terms for t in {"av", "audio", "visual", "sound", "video", "tech"}):
            expanded_terms.update({"av", "audio", "visual", "sound", "video", "tech", "production", "equipment"})

        if any(t in expanded_terms for t in {"drunk", "drink", "drinking", "alcohol", "intoxicated", "intoxication"}):
            expanded_terms.update({"alcohol", "intoxicated", "intoxication", "sobriety", "conduct", "behavior", "safety"})

        if any(t in expanded_terms for t in {"harass", "harassment", "hostile"}):
            expanded_terms.update({"harassment", "conduct", "behavior", "safety"})

        ordered = sorted(expanded_terms)
        return " ".join(ordered) if ordered else question

    @classmethod
    def _linkify_policy_lines(cls, answer: str) -> str:
        pattern = re.compile(r"^- Doc\s+(\d+)\s+\|\s*([^|]+?)\s*\|\s*relevance:\s*(.*)$", re.MULTILINE)

        def _replace(match: re.Match[str]) -> str:
            doc_id = match.group(1)
            title = match.group(2).strip()
            relevance = match.group(3).strip()

            if title.startswith("[") and "](" in title:
                return match.group(0)

            policy_url = f"{cls.POLICY_URL_PREFIX}{doc_id}"
            return f"- Doc {doc_id} | [{title}]({policy_url}) | relevance: {relevance}"

        return pattern.sub(_replace, answer)

    @app_commands.command(name="policy", description="Answer policy questions from Document table content")
    @app_commands.describe(question="Policy question to answer from documents")
    async def policy(self, interaction: discord.Interaction, question: str):
        clean_question = (question or "").strip()
        search_query = self._build_policy_search_query(clean_question)
        question_terms = self._extract_query_terms(clean_question)
        user_id = getattr(interaction.user, "id", None)
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id

        logging.info(
            "Policy question received: user_id=%s guild_id=%s channel_id=%s question=%s",
            user_id,
            guild_id,
            channel_id,
            clean_question,
        )

        if not clean_question:
            logging.info(
                "Policy question rejected (empty input): user_id=%s guild_id=%s channel_id=%s",
                user_id,
                guild_id,
                channel_id,
            )
            await interaction.response.send_message(
                "Please provide a policy question.",
                ephemeral=True,
            )
            return

        provider_name = (settings.AI_PROVIDER or "").strip().lower()
        provider_cls = get_provider(provider_name)
        if not provider_cls:
            logging.error(
                "Policy question failed: provider not registered user_id=%s provider=%s",
                user_id,
                provider_name,
            )
            await interaction.response.send_message(
                f"AI provider '{provider_name}' is not registered.",
                ephemeral=True,
            )
            return

        logging.debug(
            "Policy search initialized: user_id=%s provider=%s search_query=%s",
            user_id,
            provider_name,
            search_query,
        )

        used_fallback = False
        like_terms: list[str] = []
        query_candidates = [q for q in [clean_question, search_query] if q and q.strip()]
        deduped_queries: list[str] = []
        seen_queries = set()
        for q in query_candidates:
            normalized = q.strip().lower()
            if normalized not in seen_queries:
                seen_queries.add(normalized)
                deduped_queries.append(q)

        docs_by_id: dict[int, dict] = {}
        try:
            for search_candidate in deduped_queries:
                candidate_docs = await Database.fetch(
                    """
                    SELECT
                        "Id",
                        COALESCE("Title", '') AS title,
                        COALESCE("Category", '') AS category,
                        COALESCE("Version", '') AS version,
                        ts_rank_cd(
                            to_tsvector(
                                'english',
                                COALESCE("Title", '') || ' ' || COALESCE("Category", '') || ' ' || COALESCE("DocumentValue", '')
                            ),
                            plainto_tsquery('english', $1)
                        ) AS rank
                    FROM "Document"
                    ORDER BY rank DESC, "EditedDate" DESC NULLS LAST
                    """,
                    search_candidate,
                )

                for row in candidate_docs:
                    doc_id = int(row["Id"])
                    rank = float(row["rank"] or 0.0)
                    current = docs_by_id.get(doc_id)
                    if not current or rank > float(current.get("rank") or 0.0):
                        docs_by_id[doc_id] = row

            docs = list(docs_by_id.values())
            logging.debug(
                "Policy full-text lookup completed: user_id=%s doc_count=%s query_count=%s",
                user_id,
                len(docs),
                len(deduped_queries),
            )
        except Exception as exc:
            logging.exception("Policy document lookup failed")
            await interaction.response.send_message(
                f"Document lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not docs:
            # Fallback for natural-language phrasing that may miss full-text search tokenization.
            fallback_terms = question_terms + [t for t in self._extract_query_terms(search_query) if t not in question_terms]
            tokens = [t for t in fallback_terms if len(t.strip()) >= 2][:16]
            like_terms = [f"%{t.strip()}%" for t in tokens if t.strip()]
            if like_terms:
                used_fallback = True
                try:
                    docs = await Database.fetch(
                        """
                        SELECT
                            "Id",
                            COALESCE("Title", '') AS title,
                            COALESCE("Category", '') AS category,
                            COALESCE("Version", '') AS version,
                            0.0::float AS rank
                        FROM "Document"
                        WHERE COALESCE("Title", '') ILIKE ANY($1::text[])
                           OR COALESCE("Category", '') ILIKE ANY($1::text[])
                           OR COALESCE("DocumentValue", '') ILIKE ANY($1::text[])
                        ORDER BY "EditedDate" DESC NULLS LAST
                        """,
                        like_terms,
                    )
                    logging.debug(
                        "Policy fallback lookup completed: user_id=%s like_terms=%s doc_count=%s",
                        user_id,
                        like_terms,
                        len(docs),
                    )
                except Exception as exc:
                    logging.exception("Policy document fallback lookup failed")
                    await interaction.response.send_message(
                        f"Document lookup failed: {exc.__class__.__name__}",
                        ephemeral=True,
                    )
                    return

        if not docs:
            logging.info(
                "Policy question had no matching docs: user_id=%s search_query=%s used_fallback=%s like_terms=%s",
                user_id,
                search_query,
                used_fallback,
                like_terms,
            )
            await interaction.response.send_message(
                "I can only answer from the Document table and found no matching policy text.",
                ephemeral=True,
            )
            return

        score_terms = question_terms or self._extract_query_terms(search_query)

        def _rank_metadata(row: dict) -> tuple[float, float]:
            title = (row.get("title") or "").lower()
            category = (row.get("category") or "").lower()
            base_rank = float(row.get("rank") or 0.0)

            title_hits = sum(1 for t in score_terms if t in title)
            category_hits = sum(1 for t in score_terms if t in category)
            score = (base_rank * 20.0) + (title_hits * 5.0) + (category_hits * 3.0)
            return score, base_rank

        ranked_docs = sorted(docs, key=_rank_metadata, reverse=True)
        policy_scan_count = len(ranked_docs)
        deep_candidates = ranked_docs[: self.POLICY_DEEP_ANALYZE_LIMIT]
        deep_ids = [int(r["Id"]) for r in deep_candidates]

        docs_with_text: list[dict] = []
        if deep_ids:
            try:
                detailed_rows = await Database.fetch(
                    """
                    SELECT
                        "Id",
                        COALESCE("DocumentValue", '') AS document_value
                    FROM "Document"
                    WHERE "Id" = ANY($1::int[])
                    ORDER BY array_position($1::int[], "Id")
                    """,
                    deep_ids,
                )
                detailed_by_id = {int(r["Id"]): r for r in detailed_rows}

                for meta in deep_candidates:
                    doc_id = int(meta["Id"])
                    detailed = detailed_by_id.get(doc_id)
                    if not detailed:
                        continue

                    merged = dict(meta)
                    merged["document_value"] = detailed.get("document_value") or ""
                    docs_with_text.append(merged)
            except Exception as exc:
                logging.exception("Policy deep document lookup failed")
                await interaction.response.send_message(
                    f"Document lookup failed: {exc.__class__.__name__}",
                    ephemeral=True,
                )
                return

        if not docs_with_text:
            logging.info(
                "Policy question had no deep candidates: user_id=%s search_query=%s used_fallback=%s like_terms=%s",
                user_id,
                search_query,
                used_fallback,
                like_terms,
            )
            await interaction.response.send_message(
                "I can only answer from the Document table and found no matching policy text.",
                ephemeral=True,
            )
            return

        def _rank_row(row: dict) -> tuple[float, float]:
            title = (row.get("title") or "").lower()
            category = (row.get("category") or "").lower()
            text = str(row.get("document_value") or "").lower()
            base_rank = float(row.get("rank") or 0.0)

            overlap_count = sum(1 for t in score_terms if t in text)
            title_hits = sum(1 for t in score_terms if t in title)
            category_hits = sum(1 for t in score_terms if t in category)

            score = (base_rank * 10.0) + (overlap_count * 2.0) + (title_hits * 3.0) + (category_hits * 2.0)
            return score, base_rank

        docs = sorted(docs_with_text, key=_rank_row, reverse=True)[: self.POLICY_CONTEXT_LIMIT]

        search_terms = score_terms
        context_chunks = []
        sources = []
        allowed_doc_ids = []
        doc_debug_rows = []
        for row in docs:
            doc_id = int(row["Id"])
            title = row["title"] or "(untitled)"
            category = row["category"] or "(uncategorized)"
            version = row["version"] or "(none)"
            excerpt = self._truncate(
                self._extract_relevant_sections(str(row["document_value"]), search_terms, section_size=420, max_sections=2),
                900,
            )
            context_chunks.append(
                f"[Document Id: {doc_id}] Title: {title}\nCategory: {category}\nVersion: {version}\nRelevant section:\n{excerpt}"
            )
            sources.append(f"{doc_id}:{title}")
            allowed_doc_ids.append(str(doc_id))
            doc_debug_rows.append(
                {
                    "id": doc_id,
                    "title": title,
                    "category": category,
                    "version": version,
                    "rank": float(row["rank"]) if row["rank"] is not None else None,
                    "score_terms": score_terms,
                    "document_len": len(str(row["document_value"])),
                    "chunk_len": len(excerpt),
                }
            )

        logging.debug(
            "Policy context prepared: user_id=%s scanned=%s deep_candidates=%s context_docs=%s used_fallback=%s docs=%s",
            user_id,
            policy_scan_count,
            len(deep_candidates),
            len(docs),
            used_fallback,
            doc_debug_rows,
        )

        prompt = (
            "You are a policy locator. Use ONLY the provided document excerpts from the database. "
            "Do not use prior knowledge, web data, or any source not included below. "
            "Do NOT answer hypothetical scenarios directly (for example, do not state what punishment would happen). "
            "Do NOT infer outcomes, discipline, or consequences that are not explicitly written in the excerpts. "
            "Instead, identify the most relevant policies and explain why each is relevant to the user's question. "
            "Prefer policies with explicit language that directly matches the question's intent or terms.\n\n"
            "Response format rules:\n"
            "1) Start with: Relevant policies\n"
            "2) Return 1-4 bullet lines in this exact style: - Doc <id> | <title> | relevance: <short reason>\n"
            "3) Each reason must reference concrete wording from the excerpt (not generic guesses).\n"
            "4) If no excerpt directly addresses the question, include: - No direct policy match found in provided excerpts.\n"
            "5) Optionally add one final line starting with: Clarify: <question> if the policy text is ambiguous\n"
            "6) If excerpts are insufficient, reply exactly: I can only answer from the Document table and the provided excerpts are insufficient.\n\n"
            f"Only use document IDs from this allowed list when citing: {', '.join(allowed_doc_ids)}\n\n"
            f"Question key terms: {', '.join(score_terms) if score_terms else '(none)'}\n\n"
            f"User question:\n{clean_question}\n\n"
            "Document excerpts:\n"
            + "\n\n---\n\n".join(context_chunks)
        )

        logging.debug(
            "Policy prompt prepared: user_id=%s prompt_chars=%s allowed_doc_ids=%s",
            user_id,
            len(prompt),
            allowed_doc_ids,
        )

        try:
            try:
                provider = provider_cls(endpoint=settings.AI_ENDPOINT)
            except TypeError:
                provider = provider_cls()

            answer = await provider.complete(prompt)
            logging.debug(
                "Policy AI completion succeeded: user_id=%s raw_answer_chars=%s",
                user_id,
                len((answer or "")),
            )
        except Exception as exc:
            logging.exception("Policy AI completion failed")
            await interaction.response.send_message(
                f"AI policy response failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        final_answer = self._truncate((answer or "").strip() or "(no response)", 1600)
        final_answer = self._linkify_policy_lines(final_answer)
        source_line = self._truncate(", ".join(sources), 500)
        safe_question = self._truncate(clean_question, 300)
        template_header = "eventNinja policy matches"
        template_question = f"- question: {safe_question}"
        template_scan = f"- policy scan: scanned {policy_scan_count} total, analyzed {len(deep_candidates)} deeply, cited from {len(docs)}"
        template_sources = f"- source documents: {source_line}"
        fixed_size = len(template_header) + len(template_question) + len(template_scan) + len(template_sources) + len("- relevant policies:\n") + 12
        max_answer_len = max(200, 1900 - fixed_size)
        safe_answer = self._truncate(final_answer, max_answer_len)

        lines = [
            template_header,
            template_question,
            f"- relevant policies:\n{safe_answer}",
            template_scan,
            template_sources,
        ]
        combined = "\n".join(lines)
        if len(combined) > 1900:
            overflow = len(combined) - 1900
            safe_answer = self._truncate(safe_answer, max(200, len(safe_answer) - overflow - 5))
            lines = [
                template_header,
                template_question,
                f"- relevant policies:\n{safe_answer}",
                template_scan,
                template_sources,
            ]

        logging.info(
            "Policy response sent: user_id=%s guild_id=%s channel_id=%s question=%s response=%s",
            user_id,
            guild_id,
            channel_id,
            safe_question,
            safe_answer,
        )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class StaffNinjaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = StaffNinjaGroup()
        self.eventninja_group = EventNinjaGroup()
        self.bot.tree.add_command(self.group)
        self.bot.tree.add_command(self.eventninja_group)

    def cog_unload(self):
        self.bot.tree.remove_command(self.group.name, type=self.group.type)
        self.bot.tree.remove_command(self.eventninja_group.name, type=self.eventninja_group.type)


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffNinjaCog(bot))