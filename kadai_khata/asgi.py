"""ASGI config for kadai_khata project."""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kadai_khata.settings")

application = get_asgi_application()
