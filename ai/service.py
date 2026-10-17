"""
The one function the rest of the app calls to analyze a hazard photo.

    from ai.errors import AiRateLimited, AiUnavailable
    from ai.service import analyze_image

    try:
        result = analyze_image(photo_bytes, "image/jpeg")
    except AiRateLimited as exc:    # -> 429, exc.retry_after_seconds, don't save
        ...
    except AiUnavailable:           # -> save the report with needs_review=true
        ...

result.raw_response holds the full model answer for Report.ai_raw_response.
"""

import logging

from django.conf import settings

from ai import gemini, mock
from ai.errors import AiError, AiUnavailable
from ai.image import prepare_image
from ai.schema import AnalysisResult
from config.ai_mode import AI_MODE_LIVE, resolve_ai_mode

logger = logging.getLogger(__name__)


def current_mode() -> str:
    """'live' or 'mock'. Re-checked on every call: live needs a key AND a model."""
    return resolve_ai_mode(settings.AI_MODE, settings.GEMINI_API_KEY, settings.GEMINI_MODEL)


def analyze_image(image_bytes: bytes, mime_type: str, *, prepared: bool = False) -> AnalysisResult:
    """
    Analyze one photo. Raises only AiRateLimited or AiUnavailable.

    The photo is checked and cleaned (EXIF removed, resized) in both modes, so a non-image fails
    the same way with or without a key. Pass prepared=True if `image_bytes` already came out of
    ai.image.prepare_image (the upload endpoint does this once and also stores those bytes).
    """
    try:
        if not mime_type.startswith("image/"):
            raise AiUnavailable("not_an_image")
        jpeg_bytes = image_bytes if prepared else prepare_image(image_bytes)
        if current_mode() == AI_MODE_LIVE:
            return gemini.analyze(
                jpeg_bytes,
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_MODEL,
                thinking_level=settings.GEMINI_THINKING_LEVEL,
            )
        return mock.analyze(image_bytes, force=settings.AI_MOCK_FORCE)
    except AiError:
        raise
    # Last safety net: any bug below still becomes AiUnavailable, so the upload saves the report.
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in photo analysis: %s", type(exc).__name__)
        raise AiUnavailable("unexpected_error") from None
