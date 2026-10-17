from django.urls import path

from web import views

# Namespace: refer to these as "web:home", "web:report", "web:routes".
app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("report/", views.report, name="report"),
    path("routes/", views.routes, name="routes"),
]
