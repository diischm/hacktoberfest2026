from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie

from reports.limits import MAX_NOTE_LENGTH


def home(request):
    # Landing page. Old links to one report (/?report=<id>) now live on the map page.
    if "report" in request.GET:
        return redirect(f"{reverse('web:map')}?{request.GET.urlencode()}")
    return render(request, "web/landing.html")


# ensure_csrf_cookie: pages that POST from JS need the csrftoken cookie that api.js reads.
# map: feedback buttons on the map (E6). report: photo upload (E5).
@ensure_csrf_cookie
def map_page(request):
    return render(request, "web/map.html")


@ensure_csrf_cookie
def report(request):
    # maxlength in the HTML works before /api/meta/ has loaded; report.js then applies meta's
    # value. Both come from reports/limits.py, the same number the API enforces.
    return render(request, "web/report.html", {"max_note_length": MAX_NOTE_LENGTH})


def routes(request):
    return render(request, "web/routes.html")


@ensure_csrf_cookie
def dev_api(request):
    # Manual test page for api.js. Only exists while developing.
    if not settings.DEBUG:
        raise Http404
    return render(request, "web/dev_api.html")
