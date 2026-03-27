import socket
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db.connection import Database


class StaffNinjaGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="staffninja", description="staffNinja bot commands")

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