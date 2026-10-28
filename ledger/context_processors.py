from django.conf import settings

def demo_mode_processor(request):
    """Context processor providing DEMO_MODE flag to all templates."""
    return {
        "DEMO_MODE": getattr(settings, "DEMO_MODE", False),
    }

