import io

import pytest
from PIL import Image

from ai.errors import AiUnavailable
from ai.image import MAX_LONG_EDGE_PX, prepare_image
from tests.ai_helpers import GPS_IFD, make_photo


def test_exif_and_gps_are_removed_and_photo_is_shrunk():
    original = make_photo(size=(4000, 3000), gps=True)
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(GPS_IFD)  # test photo has GPS

    cleaned = Image.open(io.BytesIO(prepare_image(original)))

    assert cleaned.format == "JPEG"
    assert len(cleaned.getexif()) == 0
    assert "exif" not in cleaned.info
    assert max(cleaned.size) == MAX_LONG_EDGE_PX
    assert cleaned.size == (1600, 1200)  # aspect ratio kept


def test_small_photo_is_not_enlarged():
    cleaned = Image.open(io.BytesIO(prepare_image(make_photo(size=(640, 480)))))
    assert cleaned.size == (640, 480)


def test_transparent_png_becomes_jpeg():
    png = make_photo(size=(300, 200), fmt="PNG", mode="RGBA", color=(255, 0, 0, 0))
    cleaned = Image.open(io.BytesIO(prepare_image(png)))
    assert (cleaned.format, cleaned.mode) == ("JPEG", "RGB")


@pytest.mark.parametrize(
    "data",
    [b"", b"%PDF-1.4 not a photo", b"hello", make_photo()[:200]],
    ids=["empty", "pdf", "text", "truncated-jpeg"],
)
def test_non_image_is_unavailable(data):
    with pytest.raises(AiUnavailable, match="not_an_image"):
        prepare_image(data)
