import socket
from datetime import datetime, timezone
import logging
import secrets
import smtplib
from email.message import EmailMessage

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import get_settings
from db.connection import Database

settings = get_settings()


class StaffNinjaGroup(app_commands.Group):
    pending_link_challenges: dict[int, dict] = {}

    def __init__(self):
        super().__init__(name="staffninja", description="staffNinja bot commands")

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
            "- /staffninja staff: your staff profile/status from the User table",
            "- /staffninja link email:<you@example.com>: sends a verification code to your email",
            "- /staffninja verify code:<123456>: verifies code and links your Discord account",
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

        try:
            matches = await Database.fetch(
                'SELECT "Id", COALESCE("Discord", \'\') AS discord_value FROM "User" WHERE LOWER(COALESCE("Email", \'\')) = $1',
                normalized_email,
            )
        except Exception as exc:
            logging.exception("Failed email lookup for link command user_id=%s", getattr(interaction.user, "id", None))
            await interaction.response.send_message(
                f"Account lookup failed: {exc.__class__.__name__}",
                ephemeral=True,
            )
            return

        if not matches:
            await interaction.response.send_message(
                "No matching account could be verified for that email.",
                ephemeral=True,
            )
            return

        if len(matches) > 1:
            await interaction.response.send_message(
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
                await interaction.response.send_message(
                    "Your Discord account is already linked.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                "This account is already linked to a Discord identity. Please contact an admin to re-link.",
                ephemeral=True,
            )
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc).timestamp() + (settings.LINK_CODE_TTL_MINUTES * 60)

        try:
            self._send_verification_email(normalized_email, code)
        except Exception as exc:
            logging.exception("Failed to send link verification email user_id=%s", getattr(interaction.user, "id", None))
            await interaction.response.send_message(
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

        await interaction.response.send_message(
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
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class StaffNinjaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = StaffNinjaGroup()
        self.bot.tree.add_command(self.group)

    def cog_unload(self):
        self.bot.tree.remove_command(self.group.name, type=self.group.type)


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffNinjaCog(bot))