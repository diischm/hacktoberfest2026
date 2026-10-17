"""Decide whether the app talks to the real Gemini API ("live") or uses canned answers ("mock")."""

import logging

logger = logging.getLogger(__name__)

AI_MODE_LIVE = "live"
AI_MODE_MOCK = "mock"


def resolve_ai_mode(requested: str, api_key: str, model: str) -> str:
    """Return the effective AI mode. Anything unexpected falls back to mock, never crashes."""
    mode = (requested or AI_MODE_MOCK).strip().lower()

    if mode not in (AI_MODE_LIVE, AI_MODE_MOCK):
        logger.warning("AI_MODE=%r is not 'live' or 'mock'; using mock.", requested)
        return AI_MODE_MOCK

    if mode == AI_MODE_LIVE and not api_key:
        logger.warning("AI_MODE=live but GEMINI_API_KEY is empty; falling back to mock.")
        return AI_MODE_MOCK

    if mode == AI_MODE_LIVE and not model:
        logger.warning("AI_MODE=live but GEMINI_MODEL is empty; falling back to mock.")
        return AI_MODE_MOCK

    return mode
