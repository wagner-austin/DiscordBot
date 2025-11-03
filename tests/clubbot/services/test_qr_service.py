from io import BytesIO

from PIL import Image, ImageColor
from src.clubbot.services.qr_service import generate_qr_png


def test_generate_qr_png_basic() -> None:
    png = generate_qr_png(
        url="https://example.com",
        ecc="M",
        box_size=10,
        border=4,
        fill_color="#000000",
        back_color="#FFFFFF",
    )
    assert isinstance(png, (bytes | bytearray))
    assert len(png) > 1000

    with Image.open(BytesIO(png)) as img:
        assert img.format == "PNG"
        w, h = img.size
        assert w > 100 and h > 100
        # Top-left pixel should be background color
        assert img.getpixel((0, 0)) == ImageColor.getrgb("#FFFFFF")


def test_generate_qr_png_background_and_grid_alignment() -> None:
    png = generate_qr_png(
        url="https://openai.com",
        ecc="H",
        box_size=8,
        border=3,
        fill_color="#112233",
        back_color="#FEFEFE",
    )
    with Image.open(BytesIO(png)) as img:
        w, h = img.size
        # Dimensions should align to box_size grid
        assert w % 8 == 0 and h % 8 == 0
        # Corners should be background due to border
        assert img.getpixel((0, 0)) == ImageColor.getrgb("#FEFEFE")
