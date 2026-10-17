"""
Live mode: send one photo to the Gemini API and turn the answer into an AnalysisResult.

Uses google-genai, Google's official Python SDK for Gemini. `genai.Client(api_key=...)` talks to
the Gemini API (the free-tier AI Studio key), not Vertex AI. "Structured output" means we send a
JSON Schema with the request and Gemini answers with JSON of that shape.

Safety: the API key is only passed to the client. It's never logged, put in an error message or
returned. Errors are re-raised `from None`, so the SDK's original error (which holds the raw
response) isn't attached to ours and can't end up in a log by accident.
"""

import logging
import math
import re
import time

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ai.errors import AiError, AiRateLimited, AiUnavailable
from ai.prompt import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT
from ai.schema import GEMINI_RESPONSE_SCHEMA, AnalysisResult, parse_model_output

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15  # per request; the contract allows ~15 s for the whole upload
MAX_ATTEMPTS = 2  # the first call + one retry, only on a 5xx (server) error
RETRY_DELAY_SECONDS = 1.0
# Don't retry if the first attempt already used this much time (keeps the upload short).
RETRY_ONLY_IF_FAILED_WITHIN_SECONDS = 5.0


def _make_client(api_key: str) -> genai.Client:
    # Tests replace this function with a fake client, so no test ever reaches the network.
    # No retry_options: the SDK then doesn't retry by itself; we decide below.
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),  # milliseconds
    )


def analyze(jpeg_bytes: bytes, *, api_key: str, model: str) -> AnalysisResult:
    """Analyze an already-prepared JPEG (see ai.image.prepare_image)."""
    client = _make_client(api_key)
    response = _generate_with_retry(client, model, jpeg_bytes)
    raw = _raw_dict(response, model)
    try:
        result = parse_model_output(_response_text(response))
    except AiUnavailable as exc:
        exc.raw_response = raw
        logger.warning("Gemini answer rejected: %s", exc.reason)
        raise
    result.raw_response = raw
    return result


def _generate_with_retry(client, model: str, jpeg_bytes: bytes):
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_json_schema=GEMINI_RESPONSE_SCHEMA,
    )
    contents = [types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"), USER_PROMPT]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except genai_errors.APIError as exc:
            error = _map_api_error(exc)
        except (httpx.TimeoutException, TimeoutError):
            error = AiUnavailable("timeout")
        except httpx.HTTPError as exc:  # network down, DNS, connection reset…
            error = AiUnavailable(f"request_failed: {type(exc).__name__}")

        retryable = isinstance(error, AiUnavailable) and error.reason.startswith("server_error")
        quick = time.monotonic() - started < RETRY_ONLY_IF_FAILED_WITHIN_SECONDS
        if retryable and quick and attempt < MAX_ATTEMPTS:
            logger.info("Gemini %s, retrying once.", error.reason)
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        logger.warning("Gemini call failed: %s", error)
        raise error from None
    raise AssertionError("unreachable")  # pragma: no cover


def _map_api_error(exc: genai_errors.APIError) -> AiError:
    """SDK error -> our error. Only the HTTP code and status name are kept, never the message."""
    if exc.code == 429 or exc.status == "RESOURCE_EXHAUSTED":
        return AiRateLimited(retry_after_seconds=_retry_after_seconds(exc))
    status = exc.status if isinstance(exc.status, str) and exc.status.isupper() else ""
    kind = "server_error" if isinstance(exc, genai_errors.ServerError) else "api_error"
    return AiUnavailable(f"{kind} {exc.code} {status}".strip())


_DELAY_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")


def _retry_after_seconds(exc: genai_errors.APIError) -> int | None:
    """
    Gemini puts the wait time in the error body, e.g.
    {"error": {"details": [{"@type": "...google.rpc.RetryInfo", "retryDelay": "37s"}]}}.
    Falls back to a Retry-After header, else None.
    """
    body = exc.details if isinstance(exc.details, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else body
    details = error.get("details") or []
    for item in details if isinstance(details, list) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            match = _DELAY_RE.match(str(item.get("retryDelay", "")))
            if match:
                return max(1, math.ceil(float(match.group(1))))
    headers = getattr(exc.response, "headers", None) or {}
    header = headers.get("retry-after", "") if hasattr(headers, "get") else ""
    return int(header) if str(header).isdigit() else None


def _response_text(response) -> str | None:
    # .text joins the answer's text parts; it can be None or raise if the answer was blocked.
    try:
        return response.text
    except (ValueError, AttributeError):
        return None


def _raw_dict(response, model: str) -> dict:
    """The full answer as JSON-safe data, for Report.ai_raw_response (debugging only)."""
    try:
        dumped = response.model_dump(mode="json", exclude_none=True, exclude={"sdk_http_response"})
    except (ValueError, TypeError):  # Pydantic's serialization error is a ValueError
        dumped = {"text": _response_text(response)}
    return {"prompt_version": PROMPT_VERSION, "model": model, "response": dumped}
