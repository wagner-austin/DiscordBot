"""
plugins/commands/plugin.py - Plugin management command plugin.
Provides subcommands for listing, enabling, and disabling plugins using Discord's extension system.
Usage:
  !plugins list
  !plugins enable <extension>
  !plugins disable <extension>
"""

from discord.ext import commands
from bot_plugins.typing import Ctx
import logging

logger = logging.getLogger(__name__)

USAGE_PLUGINS = "Usage: !plugins <list|enable|disable> [extension]"
USAGE_ENABLE = "Usage: !plugins enable <extension>"
USAGE_DISABLE = "Usage: !plugins disable <extension>"


class PluginManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(
        name="plugins",
        aliases=["plugin"],
        invoke_without_command=True,
        case_insensitive=True,
    )
    @commands.is_owner()
    async def plugins(self, ctx: Ctx) -> None:
        await ctx.send(USAGE_PLUGINS)
        return

    @plugins.command(name="list")  # type: ignore[arg-type]
    async def list_plugins(self, ctx: Ctx) -> None:
        # List loaded extensions
        loaded = list(self.bot.extensions.keys())
        if not loaded:
            await ctx.send("No extensions loaded.")
            return

        # Group plugins by category for better organization
        categories: dict[str, list[str]] = {}
        for ext in loaded:
            # Split by dots and get the second-to-last part (e.g., 'commands' from 'bot_plugins.commands.browser')
            parts = ext.split(".")
            if len(parts) >= 3:
                category = parts[-2]  # e.g., 'commands'
                if category not in categories:
                    categories[category] = []
                categories[category].append(parts[-1])  # Add the plugin name
            else:
                # Handle plugins that don't fit the expected pattern
                if "other" not in categories:
                    categories["other"] = []
                categories["other"].append(ext)

        # Format the output with Discord markdown
        output = "**Loaded Extensions:**\n```"
        for category, plugins in sorted(categories.items()):
            # Convert category to title case for better readability
            formatted_category = category.replace("_", " ").title()
            output += f"\n{formatted_category}:\n"

            # Sort plugins alphabetically within each category
            for plugin in sorted(plugins):
                output += f"  • {plugin}\n"

        output += "```"
        await ctx.send(output)
        return

    @plugins.command(name="enable")  # type: ignore[arg-type]
    async def enable_plugin(self, ctx: Ctx, extension: str) -> None:
        try:
            await self.bot.load_extension(extension)
            await ctx.send(f"Extension '{extension}' has been enabled.")
            return
        except Exception as e:
            await ctx.send(f"Failed to enable extension '{extension}': {e}")
            return

    @plugins.command(name="disable")  # type: ignore[arg-type]
    async def disable_plugin(self, ctx: Ctx, extension: str) -> None:
        try:
            await self.bot.unload_extension(extension)
            await ctx.send(f"Extension '{extension}' has been disabled.")
            return
        except Exception as e:
            await ctx.send(f"Failed to disable extension '{extension}': {e}")
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PluginManager(bot))
