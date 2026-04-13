import logging

import discord
from discord import app_commands
from discord.ext import commands

from db.connection import Database
from services import google_groups_service
from utils.errors import GoogleGroupsError

logger = logging.getLogger(__name__)


async def _get_user_email(discord_user: discord.User | discord.Member) -> str | None:
    """Look up the linked email for a Discord user from the User table."""
    user_id = str(discord_user.id)
    candidates = {user_id, user_id.lower()}
    for attr in ("name", "global_name", "display_name"):
        val = str(getattr(discord_user, attr, "") or "").strip().lower()
        if val:
            candidates.add(val)
            candidates.add(val.lstrip("@"))

    rows = await Database.fetch(
        """
        SELECT u."Email" AS email
        FROM "User" u
        WHERE LOWER(TRIM(BOTH '@' FROM COALESCE(u."Discord", ''))) = ANY($1::text[])
        LIMIT 1
        """,
        list(candidates),
    )
    if rows:
        return rows[0]["email"]
    return None


class MailingListView(discord.ui.View):
    """Interactive view with select menus for subscribe/unsubscribe actions."""

    def __init__(self, invoker_id: int, user_email: str, groups: list[dict]):
        super().__init__(timeout=120)
        self.invoker_id = invoker_id
        self.user_email = user_email
        self.groups = groups
        self._rebuild_selects()

    def _rebuild_selects(self):
        self.clear_items()

        unsub_options = [
            discord.SelectOption(label=g["name"], value=g["email"], description=g["email"])
            for g in self.groups
            if g["is_member"] and not g["is_protected"]
        ]
        if unsub_options:
            unsub_select = discord.ui.Select(
                placeholder="Unsubscribe from...",
                min_values=1,
                max_values=len(unsub_options),
                options=unsub_options,
                custom_id="ml_unsub",
            )
            unsub_select.callback = self._on_unsubscribe
            self.add_item(unsub_select)

        sub_options = [
            discord.SelectOption(label=g["name"], value=g["email"], description=g["email"])
            for g in self.groups
            if not g["is_member"]
        ]
        if sub_options:
            sub_select = discord.ui.Select(
                placeholder="Subscribe to...",
                min_values=1,
                max_values=len(sub_options),
                options=sub_options,
                custom_id="ml_sub",
            )
            sub_select.callback = self._on_subscribe
            self.add_item(sub_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran the command can use these controls.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_unsubscribe(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected = interaction.data.get("values", [])
        results = []
        for group_email in selected:
            try:
                await google_groups_service.remove_member(group_email, self.user_email)
                results.append(f"✅ Unsubscribed from **{group_email}**")
                for g in self.groups:
                    if g["email"] == group_email:
                        g["is_member"] = False
            except GoogleGroupsError as exc:
                results.append(f"❌ Failed to unsubscribe from **{group_email}**: {exc}")
                logger.exception("Unsubscribe failed: group=%s user=%s", group_email, self.user_email)

        self._rebuild_selects()
        embed = _build_embed(self.groups)
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.followup.send("\n".join(results), ephemeral=True)

    async def _on_subscribe(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected = interaction.data.get("values", [])
        results = []
        for group_email in selected:
            try:
                await google_groups_service.add_member(group_email, self.user_email)
                results.append(f"✅ Subscribed to **{group_email}**")
                for g in self.groups:
                    if g["email"] == group_email:
                        g["is_member"] = True
            except GoogleGroupsError as exc:
                results.append(f"❌ Failed to subscribe to **{group_email}**: {exc}")
                logger.exception("Subscribe failed: group=%s user=%s", group_email, self.user_email)

        self._rebuild_selects()
        embed = _build_embed(self.groups)
        await interaction.edit_original_response(embed=embed, view=self)
        await interaction.followup.send("\n".join(results), ephemeral=True)


def _build_embed(groups: list[dict]) -> discord.Embed:
    """Build a Discord embed showing group membership status."""
    embed = discord.Embed(
        title="Mailing List Subscriptions",
        description="Your current mailing list memberships. Use the menus below to change.",
        color=discord.Color.blurple(),
    )
    for g in groups:
        if g["is_protected"]:
            status = "🔒 Required"
        elif g["is_member"]:
            status = "✅ Subscribed"
        else:
            status = "❌ Unsubscribed"

        name = g["name"]
        desc = g["description"] or g["email"]
        embed.add_field(name=f"{status}  {name}", value=desc, inline=False)

    return embed


class MailingListGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="mailinglist", description="Manage your mailing list subscriptions")

    @app_commands.command(name="list", description="View your mailing list subscriptions and opt in/out")
    async def list_groups(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        email = await _get_user_email(interaction.user)
        if not email:
            await interaction.followup.send(
                "Your Discord account is not linked to a staff record. "
                "Use `/staffninja link` to connect your account first.",
                ephemeral=True,
            )
            return

        allowed = google_groups_service.get_allowed_groups()
        if not allowed:
            await interaction.followup.send(
                "No mailing lists are configured. Contact an admin.",
                ephemeral=True,
            )
            return

        try:
            groups = await google_groups_service.get_user_groups(email)
        except GoogleGroupsError as exc:
            await interaction.followup.send(
                f"Failed to retrieve mailing lists: {exc}",
                ephemeral=True,
            )
            return

        embed = _build_embed(groups)
        view = MailingListView(invoker_id=interaction.user.id, user_email=email, groups=groups)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class MailingListCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = MailingListGroup()
        self.bot.tree.add_command(self.group)

    def cog_unload(self):
        self.bot.tree.remove_command(self.group.name, type=self.group.type)


async def setup(bot: commands.Bot):
    await bot.add_cog(MailingListCog(bot))
