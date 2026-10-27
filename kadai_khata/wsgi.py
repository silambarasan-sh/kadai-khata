"""WSGI config for kadai_khata project."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kadai_khata.settings")

application = get_wsgi_application()
