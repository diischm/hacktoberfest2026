from django.shortcuts import render


def home(request):
    return render(request, "web/home.html")


def report(request):
    return render(request, "web/report.html")


def routes(request):
    return render(request, "web/routes.html")
