from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import Config
from .qr_logic import QROptions, build_effective_qr_options
from .qr_service import generate_qr_png


@dataclass(frozen=True)
class QRResult:
    image_png: bytes
    url: str


@dataclass(frozen=True)
class QRService:
    cfg: Config
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_logger", logging.getLogger(__name__))

    def generate_qr(self, url: str) -> QRResult:
        opts = build_effective_qr_options(url, self.cfg)
        return self.generate_qr_with_options(opts)

    def generate_qr_with_options(self, opts: QROptions) -> QRResult:
        self._logger.debug(
            "QRService generating image: ecc=%s box=%s border=%s fill=%s back=%s",
            opts.ecc,
            opts.box_size,
            opts.border,
            opts.fill_color,
            opts.back_color,
        )
        png = generate_qr_png(
            url=opts.url,
            ecc=opts.ecc,
            box_size=opts.box_size,
            border=opts.border,
            fill_color=opts.fill_color,
            back_color=opts.back_color,
        )
        return QRResult(image_png=png, url=opts.url)
