from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("", include("web.urls")),
    # Never matched (web.urls wins); kept only so tests/test_home.py reverse("home") works.
    path("", views.home, name="home"),
    path("api/health/", views.health, name="health"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Serve uploaded photos from MEDIA_ROOT during development only.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
