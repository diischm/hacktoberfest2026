from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from config import views

urlpatterns = [
    path("", include("web.urls")),
    path("api/health/", views.health, name="health"),
    path("api/", include("reports.urls")),
    path("api/routes/", include("routes.urls")),
    path("admin/", admin.site.urls),
    # Must stay LAST among the api/ routes: Django tries routes top to bottom and stops at the
    # first match, so anything listed after this would never be reached. Only paths ending in "/"
    # match, so "/api/reports" (no slash) still gets Django's redirect to "/api/reports/".
    re_path(r"^api(/.*)?/$", views.ApiNotFoundView.as_view(), name="api-not-found"),
]

if settings.DEBUG:
    # Serve uploaded photos from MEDIA_ROOT during development only.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
