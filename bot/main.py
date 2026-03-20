import asyncio
import logging
import os
from discord.ext import commands
from config.settings import get_settings
from utils.logging import setup_logging

# Load config and setup logging
settings = get_settings()
setup_logging(settings.LOG_LEVEL)

intents = commands.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load cogs dynamically
async def load_cogs():
    for cog in ["staff_status", "reminders", "org_tools"]:
        try:
            await bot.load_extension(f"bot.cogs.{cog}")
        except Exception as e:
            logging.error(f"Failed to load cog {cog}: {e}")

@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")

if __name__ == "__main__":
    asyncio.run(load_cogs())
    bot.run(settings.DISCORD_TOKEN)
