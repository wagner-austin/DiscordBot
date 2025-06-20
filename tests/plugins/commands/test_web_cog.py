from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext.commands import Bot

from bot.core.containers import Container

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_bot() -> MagicMock:
    """Fixture to create a mock Bot instance."""
    bot = MagicMock(spec=Bot)
    bot.container = Container()
    return bot


@pytest.fixture
def mock_interaction() -> MagicMock:
    """Fixture to create a mock discord.Interaction."""
    interaction = AsyncMock(spec=discord.Interaction)
    interaction.channel_id = 1234567890  # Example channel ID
    interaction.response = AsyncMock(spec=discord.InteractionResponse)
    interaction.followup = AsyncMock(spec=discord.Webhook)
    return interaction


async def test_web_cog_start_command_success(
    mock_bot: MagicMock, mock_interaction: MagicMock
) -> None:
    """Test the /web start command for a successful URL navigation."""
    # Arrange
    # Patch runtime.enqueue instead of using a runner instance
    enqueue_patch = patch("bot.plugins.commands.web.BrowserRuntime.enqueue", new_callable=AsyncMock)
    mock_enqueue = enqueue_patch.start()

    from bot.plugins.commands.web import Web as WebCog

    cog = WebCog(mock_bot)
    test_url = "http://example.com"

    # Act
    await cast(Any, cog.start.callback)(cog, mock_interaction, test_url)

    # Assert
    mock_interaction.response.defer.assert_awaited_once_with(thinking=True)
    mock_enqueue.assert_awaited_once_with(mock_interaction.channel_id, "goto", test_url)
    mock_interaction.followup.send.assert_awaited_once_with(
        f"🟢 Started browser and navigated to **{test_url}**"
    )


async def test_web_cog_start_command_invalid_url(
    mock_bot: MagicMock, mock_interaction: MagicMock
) -> None:
    """Test the /web start command with an invalid URL."""
    # Arrange
    # Patch runtime.enqueue instead of using a runner instance
    enqueue_patch = patch("bot.plugins.commands.web.BrowserRuntime.enqueue", new_callable=AsyncMock)
    mock_enqueue = enqueue_patch.start()

    from bot.plugins.commands.web import Web as WebCog

    cog = WebCog(mock_bot)
    invalid_url = "notaurl"  # Not a valid URL format

    # Act
    await cast(Any, cog.start.callback)(cog, mock_interaction, invalid_url)

    # Assert
    mock_interaction.response.send_message.assert_awaited_once_with(
        f"❌ Invalid URL: '{invalid_url}' does not look like a valid host. Please include a scheme (e.g., http:// or https://).",
        ephemeral=True,
    )
    mock_enqueue.assert_not_called()
    mock_interaction.response.defer.assert_not_called()
    mock_interaction.followup.send.assert_not_called()


# TODO: Add more tests for other existing Web commands (open, screenshot, etc.)
