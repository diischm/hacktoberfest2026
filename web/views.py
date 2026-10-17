from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie

from reports.limits import MAX_NOTE_LENGTH


# ensure_csrf_cookie: pages that POST from JS need the csrftoken cookie that api.js reads.
# home: feedback buttons on the map (E6). report: photo upload (E5).
@ensure_csrf_cookie
def home(request):
    return render(request, "web/home.html")


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
