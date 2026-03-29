import asyncio
import logging
import discord
from discord.ext import commands
from config.settings import get_settings
from db.connection import Database
from utils.logging import setup_logging

# Load config and setup logging
settings = get_settings()
setup_logging(settings.LOG_LEVEL)
ALLOWED_GUILD_ID = int(settings.DISCORD_GUILD_ID)
COMMAND_RESYNC_MINUTES = max(1, int(getattr(settings, "COMMAND_RESYNC_MINUTES", 30)))
DEBUG_LOG_ENABLED = str(getattr(settings, "LOG_LEVEL", "INFO")).upper() == "DEBUG"
DEBUG_LOG_CHANNEL_NAME = "debug_log"
DEBUG_LOG_MESSAGE_LIMIT = 1800
DEBUG_LOG_QUEUE_MAXSIZE = 1000
STAFF_STATS_CATEGORY_NAME = "Staff Stats"
ACTIVE_STAFF_CHANNEL_PREFIX = "Active Staff: "
STAFF_AGREEMENTS_CHANNEL_PREFIX = "Staff Agreements: "

intents = discord.Intents.default()
intents.members = settings.DISCORD_INTENTS_MEMBERS
intents.message_content = settings.DISCORD_INTENTS_MESSAGE_CONTENT

bot = commands.Bot(command_prefix="!", intents=intents)
sync_lock = asyncio.Lock()
periodic_resync_task: asyncio.Task | None = None
debug_log_task: asyncio.Task | None = None
debug_log_handler_installed = False
debug_log_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=DEBUG_LOG_QUEUE_MAXSIZE)


class DiscordDebugLogHandler(logging.Handler):
    """Queues log records so they can be shipped to Discord asynchronously."""

    def emit(self, record: logging.LogRecord):
        if not DEBUG_LOG_ENABLED:
            return

        # Avoid recursive log loops from discord internals while posting debug logs.
        if record.name.startswith("discord") or record.name.startswith("aiohttp") or record.name.startswith("asyncio"):
            return

        try:
            rendered = self.format(record)
        except Exception:
            rendered = f"{record.levelname} {record.name} {record.getMessage()}"

        if len(rendered) > 4000:
            rendered = rendered[:3997] + "..."

        try:
            debug_log_queue.put_nowait(rendered)
        except asyncio.QueueFull:
            # Drop when saturated instead of blocking the application event loop.
            pass


def _split_log_message(message: str, limit: int = DEBUG_LOG_MESSAGE_LIMIT) -> list[str]:
    if len(message) <= limit:
        return [message]

    parts: list[str] = []
    remaining = message
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")

    if remaining:
        parts.append(remaining)
    return parts


def install_debug_log_handler_if_enabled():
    global debug_log_handler_installed
    if not DEBUG_LOG_ENABLED or debug_log_handler_installed:
        return

    handler = DiscordDebugLogHandler(level=logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.getLogger().addHandler(handler)
    debug_log_handler_installed = True


def _normalized_channel_name(value: str) -> str:
    return (value or "").strip().lower().replace("-", "_")


def _resolve_debug_channel(guild: discord.Guild) -> discord.TextChannel | None:
    exact = discord.utils.get(guild.text_channels, name=DEBUG_LOG_CHANNEL_NAME)
    if isinstance(exact, discord.TextChannel):
        return exact

    target = _normalized_channel_name(DEBUG_LOG_CHANNEL_NAME)
    for channel in guild.text_channels:
        if _normalized_channel_name(channel.name) == target:
            return channel
    return None


async def debug_log_forwarder_loop(channel: discord.TextChannel):
    while not bot.is_closed():
        message = await debug_log_queue.get()
        try:
            chunks = _split_log_message(message)
            for chunk in chunks:
                await channel.send(f"```{chunk}```")
        except Exception:
            # Avoid logging from here to prevent recursion into the same handler.
            pass


async def ensure_debug_log_forwarding():
    global debug_log_task

    if not DEBUG_LOG_ENABLED:
        return

    install_debug_log_handler_if_enabled()

    if debug_log_task is not None and not debug_log_task.done():
        return

    guild = bot.get_guild(ALLOWED_GUILD_ID)
    if guild is None:
        return

    channel = _resolve_debug_channel(guild)
    if not isinstance(channel, discord.TextChannel):
        me = guild.me
        can_manage_channels = bool(me and guild.me.guild_permissions.manage_channels)
        if can_manage_channels:
            try:
                channel = await guild.create_text_channel(DEBUG_LOG_CHANNEL_NAME, reason="staffNinja DEBUG log forwarding")
                logging.info("Created missing debug log channel #%s in guild_id=%s", DEBUG_LOG_CHANNEL_NAME, ALLOWED_GUILD_ID)
            except Exception:
                channel = None

        if not isinstance(channel, discord.TextChannel):
            logging.warning(
                "DEBUG logging is enabled but channel #%s was not found in guild_id=%s",
                DEBUG_LOG_CHANNEL_NAME,
                ALLOWED_GUILD_ID,
            )
            return

    debug_log_task = asyncio.create_task(debug_log_forwarder_loop(channel))
    logging.info("Started debug log forwarding to Discord channel #%s", DEBUG_LOG_CHANNEL_NAME)


async def _get_staff_stats_counts() -> tuple[int, int]:
    active_rows = await Database.fetch(
        'SELECT COUNT(*) AS total FROM "User" WHERE COALESCE("Status", 0) = 1'
    )
    active_staff = int(active_rows[0]["total"]) if active_rows else 0

    event_rows = await Database.fetch(
        'SELECT "StaffAgreementFormId" FROM "Event" WHERE "Status" = 1 ORDER BY "Id" DESC LIMIT 1'
    )
    if not event_rows:
        return active_staff, 0

    form_id = event_rows[0]["StaffAgreementFormId"]
    if not form_id:
        return active_staff, 0

    agreed_rows = await Database.fetch(
        '''
        SELECT COUNT(DISTINCT cf."UserId") AS total
        FROM "CompletedForm" cf
        WHERE cf."FormId" = $1
          AND EXISTS (
              SELECT 1
              FROM "CompletedAnswer" ca
              WHERE ca."CompletedFormId" = cf."Id"
          )
        ''',
        int(form_id),
    )
    agreements = int(agreed_rows[0]["total"]) if agreed_rows else 0
    return active_staff, agreements


def _discord_normalize(name: str) -> str:
    """Approximate Discord's channel name normalization (lowercase, non-alphanum/hyphen → hyphen, collapse runs)."""
    import re
    lowered = name.lower()
    cleaned = re.sub(r"[^a-z0-9-]", "-", lowered)  # spaces, colons, etc. → hyphen
    collapsed = re.sub(r"-{2,}", "-", cleaned)      # collapse consecutive hyphens
    return collapsed.strip("-")


def _find_text_channel_by_prefix(category: discord.CategoryChannel, prefix: str) -> discord.TextChannel | None:
    norm_prefix = _discord_normalize(prefix)
    for channel in category.channels:
        if isinstance(channel, discord.TextChannel) and channel.name.startswith(norm_prefix):
            return channel
    return None


def _find_voice_channel_by_prefix(category: discord.CategoryChannel, prefix: str) -> discord.VoiceChannel | None:
    norm_prefix = _discord_normalize(prefix)
    for channel in category.channels:
        if isinstance(channel, discord.VoiceChannel) and channel.name.startswith(norm_prefix):
            return channel
    return None


async def _ensure_or_update_stat_text_channel(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    prefix: str,
    value: int,
) -> None:
    desired_name = f"{prefix}{value}"
    desired_normalized = _discord_normalize(desired_name)

    # Migrate legacy voice stat channels to text channels.
    legacy_voice = _find_voice_channel_by_prefix(category, prefix)
    if legacy_voice is not None:
        await legacy_voice.delete(reason="staffNinja stats channel migrated to text channel")

    channel = _find_text_channel_by_prefix(category, prefix)
    if channel is None:
        await guild.create_text_channel(desired_normalized, category=category, reason="staffNinja stats channel")
        return

    # Channel names are already stored normalized by Discord; compare normalized forms.
    if channel.name != desired_normalized:
        await channel.edit(name=desired_normalized, reason="staffNinja stats update")


async def _purge_duplicate_stat_channels(category: discord.CategoryChannel, prefix: str) -> None:
    """Delete all text channels in *category* matching *prefix* except the first one found."""
    norm_prefix = _discord_normalize(prefix)
    matches = [
        ch for ch in category.channels
        if isinstance(ch, discord.TextChannel) and ch.name.startswith(norm_prefix)
    ]
    # Keep the first (lowest position), delete the rest.
    for ch in matches[1:]:
        try:
            await ch.delete(reason="staffNinja: removing duplicate stats channel")
            logging.info("Deleted duplicate stats channel #%s", ch.name)
        except Exception:
            logging.exception("Failed to delete duplicate stats channel #%s", ch.name)


async def ensure_staff_stats_channels():
    guild = bot.get_guild(ALLOWED_GUILD_ID)
    if guild is None:
        return

    me = guild.me
    if not me or not me.guild_permissions.manage_channels:
        logging.warning("Missing Manage Channels permission; cannot maintain Staff Stats channels")
        return

    try:
        active_staff, agreements = await _get_staff_stats_counts()
    except Exception as exc:
        logging.exception("Failed to compute staff stats counters: %s", exc)
        return

    category = discord.utils.get(guild.categories, name=STAFF_STATS_CATEGORY_NAME)
    if not isinstance(category, discord.CategoryChannel):
        try:
            category = await guild.create_category(STAFF_STATS_CATEGORY_NAME, reason="staffNinja stats category")
            logging.info("Created Staff Stats category in guild_id=%s", ALLOWED_GUILD_ID)
        except Exception as exc:
            logging.exception("Failed to create Staff Stats category: %s", exc)
            return

    # Clean up any duplicates left over from the previous naming bug.
    await _purge_duplicate_stat_channels(category, ACTIVE_STAFF_CHANNEL_PREFIX)
    await _purge_duplicate_stat_channels(category, STAFF_AGREEMENTS_CHANNEL_PREFIX)

    try:
        await _ensure_or_update_stat_text_channel(guild, category, ACTIVE_STAFF_CHANNEL_PREFIX, active_staff)
        await _ensure_or_update_stat_text_channel(guild, category, STAFF_AGREEMENTS_CHANNEL_PREFIX, agreements)
        logging.debug(
            "Updated Staff Stats channels: active_staff=%s agreements=%s guild_id=%s",
            active_staff,
            agreements,
            ALLOWED_GUILD_ID,
        )
    except Exception as exc:
        logging.exception("Failed updating Staff Stats channels: %s", exc)

# Load cogs dynamically
async def load_cogs():
    for cog in ["staff_status", "reminders", "org_tools", "staffninja", "chat_monitor"]:
        try:
            await bot.load_extension(f"bot.cogs.{cog}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}")


async def sync_app_commands(reason: str):
    async with sync_lock:
        try:
            guild = discord.Object(id=ALLOWED_GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)

            # Keep global command set empty so slash commands are not available outside the allowed guild.
            bot.tree.clear_commands(guild=None)
            cleared = await bot.tree.sync()

            logging.info(
                "Command sync complete: reason=%s guild_id=%s guild_count=%s global_count=%s",
                reason,
                ALLOWED_GUILD_ID,
                len(synced),
                len(cleared),
            )
        except Exception as exc:
            logging.exception("Guild command sync failed for %s reason=%s: %s", ALLOWED_GUILD_ID, reason, exc)


async def periodic_command_resync_loop():
    while not bot.is_closed():
        await asyncio.sleep(COMMAND_RESYNC_MINUTES * 60)
        await ensure_debug_log_forwarding()
        await ensure_staff_stats_channels()
        await sync_app_commands("periodic")

@bot.event
async def on_ready():
    global periodic_resync_task

    if not hasattr(bot, "launch_time"):
        bot.launch_time = discord.utils.utcnow()

    await sync_app_commands("on_ready")
    await ensure_debug_log_forwarding()
    await ensure_staff_stats_channels()

    if periodic_resync_task is None or periodic_resync_task.done():
        periodic_resync_task = asyncio.create_task(periodic_command_resync_loop())
        logging.info("Started periodic command resync loop: interval_minutes=%s", COMMAND_RESYNC_MINUTES)

    logging.info(f"Logged in as {bot.user}")


@bot.event
async def on_resumed():
    logging.warning("Gateway resumed; triggering command resync")
    await ensure_debug_log_forwarding()
    await ensure_staff_stats_channels()
    await sync_app_commands("on_resumed")


@bot.check
async def ensure_allowed_guild_for_prefix(ctx: commands.Context):
    if ctx.guild is None or ctx.guild.id != ALLOWED_GUILD_ID:
        logging.warning(
            "Blocked prefix command outside allowed guild: guild_id=%s user_id=%s command=%s",
            getattr(ctx.guild, "id", None),
            getattr(ctx.author, "id", None),
            getattr(ctx.command, "qualified_name", None),
        )
        return False
    return True


@bot.tree.interaction_check
async def ensure_allowed_guild_for_slash(interaction: discord.Interaction):
    if interaction.guild_id != ALLOWED_GUILD_ID:
        logging.warning(
            "Blocked slash interaction outside allowed guild: guild_id=%s user_id=%s command=%s",
            interaction.guild_id,
            getattr(interaction.user, "id", None),
            getattr(getattr(interaction, "command", None), "qualified_name", None),
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "This bot is restricted to its primary server.", ephemeral=True
            )
        return False
    return True


@bot.event
async def on_guild_join(guild: discord.Guild):
    if guild.id != ALLOWED_GUILD_ID:
        logging.warning("Left unauthorized guild: guild_id=%s name=%s", guild.id, guild.name)
        await guild.leave()


@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command: discord.app_commands.Command):
    user = interaction.user
    logging.debug(
        "Slash command completed: name=%s user=%s user_id=%s guild_id=%s channel_id=%s",
        command.qualified_name,
        str(user),
        getattr(user, "id", None),
        interaction.guild_id,
        interaction.channel_id,
    )


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    logging.exception(
        "Slash command error: user_id=%s guild_id=%s channel_id=%s error=%s",
        getattr(interaction.user, "id", None),
        interaction.guild_id,
        interaction.channel_id,
        error,
    )

if __name__ == "__main__":
    asyncio.run(load_cogs())
    bot.run(settings.DISCORD_TOKEN)
