from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Config
from ..utils.validators import validate_url


@dataclass(frozen=True)
class QROptions:
    url: str
    ecc: str
    box_size: int
    border: int
    fill_color: str
    back_color: str


logger = logging.getLogger(__name__)


def build_effective_qr_options(url: str, cfg: Config) -> QROptions:
    """Resolve user input and defaults into concrete QR options.

    Only `url` is required from the user; all other values
    come from configuration defaults.
    """
    v_url = validate_url(url)
    opts = QROptions(
        url=v_url,
        ecc=cfg.QR_DEFAULT_ERROR_CORRECTION,
        box_size=cfg.QR_DEFAULT_BOX_SIZE,
        border=cfg.QR_DEFAULT_BORDER,
        fill_color=cfg.QR_DEFAULT_FILL_COLOR,
        back_color=cfg.QR_DEFAULT_BACK_COLOR,
    )
    logger.debug(
        "Resolved QR options: url=%s ecc=%s box=%s border=%s fill=%s back=%s",
        opts.url,
        opts.ecc,
        opts.box_size,
        opts.border,
        opts.fill_color,
        opts.back_color,
    )
    return opts
