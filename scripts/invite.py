import os

from dotenv import find_dotenv, load_dotenv


def main() -> None:
    load_dotenv(find_dotenv(), override=True)
    app_id = os.getenv("DISCORD_APPLICATION_ID")
    perms = os.getenv("DISCORD_PERMISSIONS", "2147601408")
    scopes = "bot%20applications.commands"

    if not app_id:
        print("Set DISCORD_APPLICATION_ID in your environment to generate an invite URL.")
        raise SystemExit(1)

    guild_install = f"https://discord.com/api/oauth2/authorize?client_id={app_id}&permissions={perms}&scope={scopes}"
    print("Guild Install (bot + commands):")
    print(guild_install)


if __name__ == "__main__":
    main()
