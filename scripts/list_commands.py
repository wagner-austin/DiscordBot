from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from dotenv import find_dotenv, load_dotenv

API_BASE = "https://discord.com/api/v10"


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bot {token}",
        "User-Agent": "discord-club-bot (commands-inspector)",
        "Accept": "application/json",
    }


def _get(url: str, headers: dict[str, str]) -> Any:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8"))


def list_global(app_id: str, token: str) -> list[dict[str, Any]]:
    url = f"{API_BASE}/applications/{app_id}/commands"
    data: Any = _get(url, _auth_headers(token))
    assert isinstance(data, list)
    return [dict(x) for x in data]


def list_guild(app_id: str, guild_id: str, token: str) -> list[dict[str, Any]]:
    url = f"{API_BASE}/applications/{app_id}/guilds/{guild_id}/commands"
    data: Any = _get(url, _auth_headers(token))
    assert isinstance(data, list)
    return [dict(x) for x in data]


def fmt_cmd(cmd: dict[str, Any]) -> str:
    name = cmd.get("name")
    cid = cmd.get("id")
    ctype = cmd.get("type")
    dm = cmd.get("dm_permission")
    version = cmd.get("version")
    parts = [f"name={name}", f"id={cid}", f"type={ctype}"]
    if dm is not None:
        parts.append(f"dm_permission={dm}")
    if version is not None:
        parts.append(f"version={version}")
    return ", ".join(parts)


def parse_env_ids(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for part in text.replace("\n", " ").replace(",", " ").split():
        if part.strip():
            out.append(part.strip())
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Discord application commands (global/guild)")
    parser.add_argument(
        "--global",
        dest="show_global",
        action="store_true",
        help="List global commands",
    )
    parser.add_argument(
        "--guild",
        dest="guild_ids",
        action="append",
        help="Guild ID to list (repeatable)",
    )
    parser.add_argument(
        "--from-env",
        dest="from_env",
        action="store_true",
        help="Also load guild IDs from DISCORD_GUILD_ID/DISCORD_GUILD_IDS",
    )
    return parser.parse_args()


def _load_ids_from_env() -> list[str]:
    env_single = os.getenv("DISCORD_GUILD_ID", "").strip()
    env_multi = os.getenv("DISCORD_GUILD_IDS", "").strip()
    out: list[str] = []
    out.extend([env_single] if env_single else [])
    out.extend(parse_env_ids(env_multi))
    return out


def _resolve_env() -> tuple[str, str]:
    # Load .env so env vars are available when invoked via Makefile
    load_dotenv(find_dotenv(), override=True)
    token = os.getenv("DISCORD_TOKEN", "").strip()
    app_id = os.getenv("DISCORD_APPLICATION_ID", "").strip()
    return token, app_id


def _print_commands(app_id: str, token: str, show_global: bool, guild_ids: list[str]) -> None:
    if show_global:
        cmds = list_global(app_id, token)
        print(f"Global commands: {len(cmds)}")
        for c in cmds:
            print(f"  - {fmt_cmd(c)}")

    for gid in guild_ids:
        gid = gid.strip()
        if not gid:
            continue
        cmds = list_guild(app_id, gid, token)
        print(f"Guild {gid} commands: {len(cmds)}")
        for c in cmds:
            print(f"  - {fmt_cmd(c)}")


def main() -> int:
    args = _parse_args()
    token, app_id = _resolve_env()
    if not token or not app_id:
        print(
            "DISCORD_TOKEN and DISCORD_APPLICATION_ID must be set in env/.env",
            file=sys.stderr,
        )
        return 2

    guild_ids: list[str] = []
    if args.guild_ids:
        guild_ids.extend(args.guild_ids)
    if args.from_env:
        guild_ids.extend(_load_ids_from_env())

    try:
        _print_commands(app_id, token, args.show_global, guild_ids)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTPError {e.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - network/IO
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI utility
    raise SystemExit(main())
