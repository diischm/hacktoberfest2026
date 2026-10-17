"""
The only two errors `ai.service.analyze_image` raises. The upload endpoint catches exactly these.

Messages are always short, fixed strings written by us: never the raw Gemini response and never
the API key, so they're safe to log.
"""


class AiError(Exception):
    """Base class, so callers can catch both with one `except AiError`."""


class AiRateLimited(AiError):
    """Gemini free-tier quota hit (HTTP 429). Upload answers 429 and does NOT create a report."""

    def __init__(self, retry_after_seconds: int | None = None):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"AI rate limited (retry after {retry_after_seconds} s)")


class AiUnavailable(AiError):
    """
    Any other failure: timeout, bad answer, API error, not an image. Upload still creates the
    report, with needs_review=true (see API_CONTRACT.md, E5).

    `raw_response` is whatever Gemini answered (if anything), for Report.ai_raw_response.
    """

    def __init__(self, reason: str, raw_response: dict | None = None):
        self.reason = reason
        self.raw_response = raw_response
        super().__init__(f"AI unavailable: {reason}")
