from __future__ import annotations

from src.clubbot.config import Config
from src.clubbot.services.qr_app import QRService
from src.clubbot.services.qr_logic import QROptions


def test_generate_qr_calls_build_and_returns_result(monkeypatch) -> None:
    cfg = Config(
        DISCORD_TOKEN="x",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=2,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
    )
    svc = QRService(cfg)

    called = {"built": False, "png": False}

    def _fake_build(url: str, cfg_arg: object) -> QROptions:
        called["built"] = True
        return QROptions(
            url=url,
            ecc="M",
            box_size=10,
            border=2,
            fill_color="#000000",
            back_color="#FFFFFF",
        )

    def _fake_png(
        *,
        url: str,
        ecc: str,
        box_size: int,
        border: int,
        fill_color: str,
        back_color: str,
    ) -> bytes:
        called["png"] = True
        return b"\x89PNG\r\n\x1a\n"

    import src.clubbot.services.qr_app as app_mod

    monkeypatch.setattr(app_mod, "build_effective_qr_options", _fake_build)
    monkeypatch.setattr(app_mod, "generate_qr_png", _fake_png)

    out = svc.generate_qr("https://example.com")
    assert out.url == "https://example.com"
    assert called["built"] and called["png"]
