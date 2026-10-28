"""URL configuration for kadai_khata project."""

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path


def healthz(request):
    """Health check endpoint returning system status and Meta integration mode."""
    return JsonResponse({
        "status": "ok",
        "mode": getattr(settings, "META_MODE", "mock"),
    })


urlpatterns = [
    re_path(r"^healthz/?$", healthz, name="healthz"),
    path("", include("ledger.urls")),
]

if getattr(settings, "DJANGO_ENABLE_ADMIN", False):
    urlpatterns.insert(0, path("admin/", admin.site.urls))
