"""Prepare a photo before analysis: check it's really an image, drop metadata, shrink it."""

import io
import struct

from PIL import Image, ImageOps

from ai.errors import AiUnavailable

MAX_LONG_EDGE_PX = 1600
JPEG_QUALITY = 85


def prepare_image(image_bytes: bytes) -> bytes:
    """
    Return a clean JPEG: long edge at most 1600 px, no EXIF (so no GPS position, camera, etc.).

    Raises AiUnavailable if the bytes aren't an image Pillow can read.
    """
    try:
        # verify() checks the file structure without decoding it, but leaves the object
        # unusable, so the image is opened a second time to actually read the pixels.
        Image.open(io.BytesIO(image_bytes)).verify()
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Phones store "rotate me" in EXIF. Apply it now, because EXIF is dropped below.
            img = ImageOps.exif_transpose(img)
            img = _to_rgb(img)
            img.thumbnail((MAX_LONG_EDGE_PX, MAX_LONG_EDGE_PX))  # keeps the aspect ratio
            out = io.BytesIO()
            # A new JPEG without exif=... has no EXIF at all.
            img.save(out, format="JPEG", quality=JPEG_QUALITY)
    # Pillow raises different errors for different broken files; these are the ones it uses.
    except (OSError, SyntaxError, ValueError, EOFError, struct.error, Image.DecompressionBombError):
        raise AiUnavailable("not_an_image") from None
    return out.getvalue()


def _to_rgb(img: Image.Image) -> Image.Image:
    """JPEG has no transparency: put transparent images (PNG/WebP) on a white background."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")
