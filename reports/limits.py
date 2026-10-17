"""Numbers from docs/plan/API_CONTRACT.md that the API both publishes (/api/meta/) and enforces."""

MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB
ACCEPTED_PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_NOTE_LENGTH = 500

# Placeholder demo area (Macedonia Square) until the real one is confirmed.
MAP_CENTER = {"lat": 41.9962, "lng": 21.4316}
MAP_ZOOM = 15
MAP_BOUNDS = {"min_lat": 41.95, "min_lng": 21.30, "max_lat": 42.05, "max_lng": 21.55}

# E3 returns at most this many reports and sets "truncated": true when more matched.
MAX_REPORTS_PER_LIST = 500

# E7 segments, E10 bike parking: at most this many features per response.
MAX_SEGMENTS_PER_LIST = 1000
MAX_BIKE_PARKING_PER_LIST = 500
# Reports considered when scoring E7 segments (newest first).
MAX_HAZARDS_PER_SEGMENT_LIST = 500
