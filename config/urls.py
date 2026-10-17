from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from config import views

urlpatterns = [
    path("", views.home, name="home"),
    path("api/health/", views.health, name="health"),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    # Serve uploaded photos from MEDIA_ROOT during development only.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
