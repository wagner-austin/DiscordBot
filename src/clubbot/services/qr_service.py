from __future__ import annotations

import io
import logging

import qrcode
from PIL import ImageColor
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import SquareModuleDrawer

ECC_MAP = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}


logger = logging.getLogger(__name__)


def generate_qr_png(
    url: str,
    ecc: str,
    box_size: int,
    border: int,
    fill_color: str,
    back_color: str,
) -> bytes:
    logger.debug(
        "Generating QR: ecc=%s box=%s border=%s fill=%s back=%s",
        ecc,
        box_size,
        border,
        fill_color,
        back_color,
    )
    qr = qrcode.QRCode(
        version=None,
        error_correction=ECC_MAP[ecc],
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Normalize colors to RGB tuples for PIL
    front = ImageColor.getrgb(fill_color)
    back = ImageColor.getrgb(back_color)

    image = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=SquareModuleDrawer(),
        color_mask=SolidFillColorMask(back_color=back, front_color=front),
    )

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
