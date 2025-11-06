from __future__ import annotations

from types import SimpleNamespace

from src.clubbot.orchestrator import BotOrchestrator


def test_preflight_no_application_id(monkeypatch) -> None:
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)
    orch = BotOrchestrator(SimpleNamespace(cfg=SimpleNamespace(DISCORD_TOKEN="abc.def.ghi")))
    # Should no-op when env is absent
    orch._preflight_token_check()


def test_preflight_app_id_matches_token(monkeypatch) -> None:
    # '999' base64url is 'OTk5OQ'
    token = "OTk5OQ.x.y"
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "999")
    orch = BotOrchestrator(SimpleNamespace(cfg=SimpleNamespace(DISCORD_TOKEN=token)))
    orch._preflight_token_check()  # should not raise


def test_run_invokes_preflight_match_branch(monkeypatch) -> None:
    # Ensure the preflight check runs inside run() with a matching token/app id
    token = "OTk5OQ.x.y"  # base64url("999").
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "999")
    orch = BotOrchestrator(SimpleNamespace(cfg=SimpleNamespace(DISCORD_TOKEN=token)))

    class _Bot:
        def run(self, tok: str) -> None:  # pragma: no cover - trivial
            assert tok == token

    monkeypatch.setattr(orch, "build_bot", lambda: _Bot(), raising=True)
    orch.run()  # exercises preflight branch with equal app id
