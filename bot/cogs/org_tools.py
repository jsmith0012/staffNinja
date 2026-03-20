from discord.ext import commands

class OrgToolsCog(commands.Cog):
    """Organization utility commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def orgtool(self, ctx):
        # TODO: Implement org utility
        await ctx.send("[Org tools feature coming soon]")

async def setup(bot):
    await bot.add_cog(OrgToolsCog(bot))
