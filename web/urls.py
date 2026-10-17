from django.urls import path

from web import views

# Namespace: refer to these as "web:home", "web:map", "web:report", "web:routes".
app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),  # landing page
    path("map/", views.map_page, name="map"),
    path("report/", views.report, name="report"),
    path("routes/", views.routes, name="routes"),
    path("dev/api/", views.dev_api, name="dev-api"),  # 404 unless DEBUG
]
