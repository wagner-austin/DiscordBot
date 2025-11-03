from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import discord
import pytest
from discord.ext import commands
from src.clubbot.cogs.invite import InviteCog, _resolve_app_id
from src.clubbot.config import Config


class _FakeResponse:
    def __init__(self, parent: _FakeInteraction) -> None:
        self._done = False
        self._parent = parent

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool = False) -> None:  # pragma: no cover - not used here
        self._done = True

    async def send_message(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ) -> None:
        self._done = True
        self._parent.calls.append(
            {
                "message": content,
                "embed": embed,
                "ephemeral": ephemeral,
                "where": "response",
            }
        )


class _FakeFollowup:
    def __init__(self, parent: _FakeInteraction) -> None:
        self._parent = parent

    async def send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        ephemeral: bool = False,
    ) -> None:
        self._parent.calls.append(
            {
                "message": content,
                "embed": embed,
                "ephemeral": ephemeral,
                "where": "followup",
            }
        )


class _FakeInteraction:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = _FakeResponse(self)
        self.followup = _FakeFollowup(self)


def _cfg() -> Config:
    return Config(
        DISCORD_TOKEN="x",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=1,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
    )


def _extract_invite_field(embed: discord.Embed) -> str:
    fields = getattr(embed, "fields", [])
    assert fields and isinstance(fields[0].value, str)
    return str(fields[0].value)


def test_resolve_app_id_prefers_application_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    bot_like = SimpleNamespace(application_id=1234, user=None)
    app_id = _resolve_app_id(bot_like)
    assert app_id == 1234


def test_resolve_app_id_falls_back_to_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    bot_like = SimpleNamespace(application_id=None, user=SimpleNamespace(id=5678))
    app_id = _resolve_app_id(bot_like)
    assert app_id == 5678


def test_resolve_app_id_uses_env_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "9012")
    bot_like = SimpleNamespace(application_id=None, user=None)
    app_id = _resolve_app_id(bot_like)
    assert app_id == 9012


def test_resolve_app_id_none_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    bot_like = SimpleNamespace()  # no attributes
    app_id = _resolve_app_id(bot_like)
    assert app_id is None


@pytest.mark.asyncio
async def test_invite_sends_embed_via_response(monkeypatch: pytest.MonkeyPatch) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg()
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "13579")
    monkeypatch.setenv("DISCORD_PERMISSIONS", "24680")

    cog = InviteCog(bot, cfg)
    inter = _FakeInteraction()
    await cog.invite.callback(cog, inter)

    assert inter.calls, "Expected a response call"
    last = inter.calls[-1]
    assert last["where"] == "response"
    assert isinstance(last["embed"], discord.Embed)
    url = _extract_invite_field(last["embed"])
    assert "client_id=13579" in url and "permissions=24680" in url
    assert "scope=bot%20applications.commands" in url
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_invite_sends_embed_via_followup_when_response_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg()
    monkeypatch.delenv("DISCORD_PERMISSIONS", raising=False)  # use default perms
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "24680")

    cog = InviteCog(bot, cfg)
    inter = _FakeInteraction()
    # Simulate that response has already been used elsewhere
    inter.response._done = True  # flip the flag to force followup path
    await cog.invite.callback(cog, inter)

    assert inter.calls, "Expected a followup call"
    last = inter.calls[-1]
    assert last["where"] == "followup"
    assert isinstance(last["embed"], discord.Embed)
    # Default permission should be present when env was not set
    url = _extract_invite_field(last["embed"])
    assert "client_id=24680" in url and "permissions=2147601408" in url
    assert last["ephemeral"] is True


@pytest.mark.asyncio
async def test_invite_reports_missing_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    cfg = _cfg()
    # Ensure no env fallback is available
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)

    cog = InviteCog(bot, cfg)
    inter = _FakeInteraction()
    await cog.invite.callback(cog, inter)

    assert inter.calls, "Expected a response call"
    last = inter.calls[-1]
    assert last["where"] == "response"
    assert isinstance(last["message"], str) and "Could not determine" in last["message"]
    assert last.get("embed") is None
    assert last["ephemeral"] is True
