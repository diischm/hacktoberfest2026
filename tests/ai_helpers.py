"""Shared helpers for the ai tests: make test photos and a fake Gemini client (no network)."""

import io

from google.genai import types
from PIL import Image

GPS_IFD = 0x8825
EXIF_MAKE = 0x010F


def make_photo(size=(800, 600), color="gray", fmt="JPEG", mode="RGB", gps=False) -> bytes:
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[EXIF_MAKE] = "TestCam"
        gps_ifd = exif.get_ifd(GPS_IFD)
        gps_ifd[1] = "N"
        gps_ifd[2] = (41.0, 59.0, 46.0)  # a position in Skopje
        img.save(buf, fmt, exif=exif)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def gemini_response(text: str) -> types.GenerateContentResponse:
    """A real SDK response object holding `text`, built locally."""
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))
        ]
    )


class FakeClock:
    """Replaces time.monotonic/time.sleep in ai.gemini: time only moves when we say so."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeModels:
    def __init__(self, outcomes, on_call=None):
        self.outcomes = list(outcomes)
        self.calls = []
        self.on_call = on_call

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_call:
            self.on_call()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    """Stands in for genai.Client: each call returns (or raises) the next outcome."""

    def __init__(self, *outcomes, on_call=None):
        self.models = FakeModels(outcomes, on_call)
