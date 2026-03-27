import asyncio
import logging
import discord
from discord.ext import commands
from config.settings import get_settings
from utils.logging import setup_logging

# Load config and setup logging
settings = get_settings()
setup_logging(settings.LOG_LEVEL)
ALLOWED_GUILD_ID = int(settings.DISCORD_GUILD_ID)
COMMAND_RESYNC_MINUTES = max(1, int(getattr(settings, "COMMAND_RESYNC_MINUTES", 30)))

intents = discord.Intents.default()
intents.members = settings.DISCORD_INTENTS_MEMBERS
intents.message_content = settings.DISCORD_INTENTS_MESSAGE_CONTENT

bot = commands.Bot(command_prefix="!", intents=intents)
sync_lock = asyncio.Lock()
periodic_resync_task: asyncio.Task | None = None

# Load cogs dynamically
async def load_cogs():
    for cog in ["staff_status", "reminders", "org_tools", "staffninja"]:
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
        await sync_app_commands("periodic")

@bot.event
async def on_ready():
    global periodic_resync_task

    if not hasattr(bot, "launch_time"):
        bot.launch_time = discord.utils.utcnow()

    await sync_app_commands("on_ready")

    if periodic_resync_task is None or periodic_resync_task.done():
        periodic_resync_task = asyncio.create_task(periodic_command_resync_loop())
        logging.info("Started periodic command resync loop: interval_minutes=%s", COMMAND_RESYNC_MINUTES)

    logging.info(f"Logged in as {bot.user}")


@bot.event
async def on_resumed():
    logging.warning("Gateway resumed; triggering command resync")
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
