from src.clubbot.config import Config
from src.clubbot.services.qr_logic import build_effective_qr_options


def make_cfg() -> Config:
    return Config(
        DISCORD_TOKEN="test",
        DISCORD_GUILD_ID=None,
        DISCORD_GUILD_IDS=[],
        LOG_LEVEL="INFO",
        QRCODE_RATE_LIMIT=1,
        QRCODE_RATE_WINDOW_SECONDS=1,
        QR_DEFAULT_ERROR_CORRECTION="M",
        QR_DEFAULT_BOX_SIZE=10,
        QR_DEFAULT_BORDER=4,
        QR_DEFAULT_FILL_COLOR="#000000",
        QR_DEFAULT_BACK_COLOR="#FFFFFF",
        QR_PUBLIC_RESPONSES=True,
    )


def test_build_effective_qr_options_defaults():
    cfg = make_cfg()
    opts = build_effective_qr_options("https://example.com", cfg)
    assert opts.url == "https://example.com"
    assert opts.ecc == cfg.QR_DEFAULT_ERROR_CORRECTION
    assert opts.box_size == cfg.QR_DEFAULT_BOX_SIZE
    assert opts.border == cfg.QR_DEFAULT_BORDER
    assert opts.fill_color == cfg.QR_DEFAULT_FILL_COLOR
    assert opts.back_color == cfg.QR_DEFAULT_BACK_COLOR


def test_build_effective_qr_options_accepts_bare_hostname():
    cfg = make_cfg()
    opts = build_effective_qr_options("example.com", cfg)
    assert opts.url == "https://example.com"
