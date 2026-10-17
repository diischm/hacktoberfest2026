"""Settings for pytest: same as the normal settings, but the real Gemini API is never reachable."""

from config.settings import *

# Even if a developer's .env has AI_MODE=live and a real key, tests stay offline.
GEMINI_API_KEY = ""
AI_MODE = "mock"
AI_MOCK_FORCE = ""
GEMINI_THINKING_LEVEL = ""
