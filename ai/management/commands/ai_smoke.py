"""
`python manage.py ai_smoke <image>`: analyze one photo and print the result as JSON.

For checking your Gemini setup by hand. In live mode this makes ONE real API call (uses free-tier
quota). Never run it from tests or CI.
"""

import json
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ai.errors import AiRateLimited, AiUnavailable
from ai.service import analyze_image, current_mode


class Command(BaseCommand):
    help = "Analyze one photo with the configured AI mode and print the result as JSON."

    def add_arguments(self, parser):
        parser.add_argument("image_path", help="Path to a JPEG, PNG or WebP photo")
        parser.add_argument(
            "--raw", action="store_true", help="Also print the full model answer (debugging)"
        )

    def handle(self, *args, **options):
        path = Path(options["image_path"])
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        mode = current_mode()
        output = {"mode": mode, "model": settings.GEMINI_MODEL if mode == "live" else None}
        try:
            result = analyze_image(path.read_bytes(), mime_type)
        except AiRateLimited as exc:
            output["error"] = {
                "type": "AiRateLimited",
                "retry_after_seconds": exc.retry_after_seconds,
            }
        except AiUnavailable as exc:
            output["error"] = {"type": "AiUnavailable", "reason": exc.reason}
            if options["raw"]:
                output["raw_response"] = exc.raw_response
        else:
            output["result"] = result.model_dump()
            if options["raw"]:
                output["raw_response"] = result.raw_response

        self.stdout.write(json.dumps(output, indent=2, ensure_ascii=False))
        if "error" in output:
            raise CommandError("Analysis failed (see above).")
