import logging

import discord

import db.queries
from services import google_groups_service
from utils.errors import GoogleGroupsError

logger = logging.getLogger(__name__)


async def _is_leadership(discord_user: discord.User | discord.Member) -> bool:
    """Check if a Discord user holds any leadership staff position."""
    user_id = str(discord_user.id)
    candidates = {user_id, user_id.lower()}
    for attr in ("name", "global_name", "display_name"):
        val = str(getattr(discord_user, attr, "") or "").strip().lower()
        if val:
            candidates.add(val)
            candidates.add(val.lstrip("@"))

    return await db.queries.is_leadership_user(list(candidates))


async def _get_user_email(discord_user: discord.User | discord.Member) -> str | None:
    """Look up the linked email for a Discord user from the User table."""
    user_id = str(discord_user.id)
    candidates = {user_id, user_id.lower()}
    for attr in ("name", "global_name", "display_name"):
        val = str(getattr(discord_user, attr, "") or "").strip().lower()
        if val:
            candidates.add(val)
            candidates.add(val.lstrip("@"))

    return await db.queries.get_user_email_by_discord(list(candidates))


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
