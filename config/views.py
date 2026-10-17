from django.conf import settings
from django.shortcuts import render
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    # Only the effective mode: never the key, nor whether one is configured.
    return Response({"status": "ok", "ai_mode": settings.AI_MODE})


def home(request):
    return render(request, "home.html")
