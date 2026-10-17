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
# Hard cap for one analyze() call, retry included. The frontend gives up after 30 s, so this
# leaves room for the upload itself and saving the report. A retry only starts if a full attempt
# (delay + TIMEOUT_SECONDS) still fits before the deadline; otherwise we give up right away.
DEADLINE_SECONDS = 20

# "Thinking" = the model reasons before answering: better on hard tasks, but slower. Gemini 3
# models accept a thinking_level; older ones (2.5) reject it with a 400. So it's opt-in via
# settings.GEMINI_THINKING_LEVEL, and empty means "send nothing, use the model's default".
THINKING_LEVELS = {
    "minimal": types.ThinkingLevel.MINIMAL,
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}

# Tests replace these with a fake clock, so the deadline can be tested without real waiting.
_clock = time.monotonic
_sleep = time.sleep


def _make_client(api_key: str) -> genai.Client:
    # Tests replace this function with a fake client, so no test ever reaches the network.
    # No retry_options: the SDK then doesn't retry by itself; we decide below.
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000),  # milliseconds
    )


def analyze(
    jpeg_bytes: bytes, *, api_key: str, model: str, thinking_level: str = ""
) -> AnalysisResult:
    """Analyze an already-prepared JPEG (see ai.image.prepare_image)."""
    deadline = _clock() + DEADLINE_SECONDS
    client = _make_client(api_key)
    config = _generate_config(thinking_level)
    response = _generate_with_retry(client, model, jpeg_bytes, config, deadline)
    raw = _raw_dict(response, model)
    try:
        result = parse_model_output(_response_text(response))
    except AiUnavailable as exc:
        exc.raw_response = raw
        logger.warning("Gemini answer rejected: %s", exc.reason)
        raise
    result.raw_response = raw
    return result


def _generate_config(thinking_level: str) -> types.GenerateContentConfig:
    level = THINKING_LEVELS.get(thinking_level)
    if thinking_level and level is None:
        logger.warning(
            "GEMINI_THINKING_LEVEL=%r is not one of %s; ignoring it.",
            thinking_level,
            ", ".join(THINKING_LEVELS),
        )
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_json_schema=GEMINI_RESPONSE_SCHEMA,
        thinking_config=types.ThinkingConfig(thinking_level=level) if level else None,
    )


def _generate_with_retry(client, model: str, jpeg_bytes: bytes, config, deadline: float):
    contents = [types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"), USER_PROMPT]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except genai_errors.APIError as exc:
            error = _map_api_error(exc)
        except (httpx.TimeoutException, TimeoutError):
            error = AiUnavailable("timeout")
        except httpx.HTTPError as exc:  # network down, DNS, connection reset…
            error = AiUnavailable(f"request_failed: {type(exc).__name__}")

        retryable = isinstance(error, AiUnavailable) and error.reason.startswith("server_error")
        time_left = deadline - _clock()
        retry_fits = time_left >= RETRY_DELAY_SECONDS + TIMEOUT_SECONDS
        if retryable and retry_fits and attempt < MAX_ATTEMPTS:
            logger.info("Gemini %s, retrying once.", error.reason)
            _sleep(RETRY_DELAY_SECONDS)
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
