import pytest


@pytest.fixture(autouse=True)
def temp_media_root(settings, tmp_path):
    # Uploaded photos go to a throwaway folder, never into the repo's media/.
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def clear_cache():
    # The upload throttle counts requests in Django's cache; start every test at zero.
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
