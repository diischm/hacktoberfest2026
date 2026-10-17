from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    # Only the effective mode: never the key, nor whether one is configured.
    return Response({"status": "ok", "ai_mode": settings.AI_MODE})


class ApiNotFoundView(APIView):
    """Unknown /api/ path -> contract-shaped 404 (via config/exceptions.py), for every method."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def initial(self, request, *args, **kwargs):
        # initial() runs before the get()/post()/... handler, so no method ever gets a 405 here.
        raise NotFound()
