from django.urls import path

from reports import views

# Mounted under /api/ by config/urls.py.
urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="api-meta"),
    path("reports/", views.ReportListView.as_view(), name="api-report-list"),
    path("reports/<str:pk>/", views.ReportDetailView.as_view(), name="api-report-detail"),
    path("segments/", views.SegmentListView.as_view(), name="api-segment-list"),
    path("bike-parking/", views.BikeParkingListView.as_view(), name="api-bike-parking-list"),
]
