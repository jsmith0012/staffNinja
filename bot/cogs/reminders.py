from discord.ext import commands

class RemindersCog(commands.Cog):
    """Reminder scheduling commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def remind(self, ctx):
        # TODO: Implement reminder scheduling
        await ctx.send("[Reminder feature coming soon]")

async def setup(bot):
    await bot.add_cog(RemindersCog(bot))
