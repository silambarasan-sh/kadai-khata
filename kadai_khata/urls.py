"""URL configuration for kadai_khata project."""

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path

SVG_FAVICON = (
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">"""
    """<rect width="32" height="32" rx="8" fill="#1e3a8a"/>"""
    """<text x="16" y="22" font-size="18" text-anchor="middle" fill="#ffffff" """
    """font-family="system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" """
    """font-weight="bold">₹</text></svg>"""
)


def favicon_view(request):
    """Serve inline SVG favicon."""
    return HttpResponse(SVG_FAVICON, content_type="image/svg+xml")


def healthz(request):
    """Health check endpoint returning system status and Meta integration mode."""
    return JsonResponse({
        "status": "ok",
        "mode": getattr(settings, "META_MODE", "mock"),
    })


urlpatterns = [
    re_path(r"^healthz/?$", healthz, name="healthz"),
    path("favicon.ico", favicon_view, name="favicon"),
    path("", include("ledger.urls")),
]

if getattr(settings, "DJANGO_ENABLE_ADMIN", False):
    urlpatterns.insert(0, path("admin/", admin.site.urls))

