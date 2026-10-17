"""Upload throttle: at most N POSTs per minute per IP (rate in REST_FRAMEWORK settings)."""

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class ReportUploadThrottle(SimpleRateThrottle):
    scope = "report_upload"

    def get_rate(self):
        # Read on every request (DRF's ScopedRateThrottle reads it once at import), so tests can
        # change the rate with the `settings` fixture.
        return api_settings.DEFAULT_THROTTLE_RATES[self.scope]

    def get_cache_key(self, request, view):
        # By IP, not by session: dropping the session cookie would reset a per-session counter.
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
