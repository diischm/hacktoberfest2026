from django.urls import path

from routes import views

# Mounted under /api/routes/ by config/urls.py.
urlpatterns = [
    path("scenarios/", views.ScenarioListView.as_view(), name="api-route-scenarios"),
    path("compare/", views.CompareView.as_view(), name="api-route-compare"),
]
