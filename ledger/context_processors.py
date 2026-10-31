import os
from django.conf import settings


def demo_mode_processor(request):
    """Context processor providing DEMO_MODE flag and base URL to all templates."""
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        app_base_url = render_url.rstrip("/")
        if not app_base_url.startswith("http"):
            app_base_url = f"https://{app_base_url}"
    else:
        app_base_url = request.build_absolute_uri("/").rstrip("/")

    return {
        "DEMO_MODE": getattr(settings, "DEMO_MODE", False),
        "APP_BASE_URL": app_base_url,
    }


