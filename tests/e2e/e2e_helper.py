"""Helper utilities for Playwright E2E browser tests without requiring external TCP sockets.

Routes all HTTP and static requests from Chromium in-memory to Django's test Client.
Allows fully sandboxed, fast, deterministic browser testing with pixel-level DOM inspection,
device emulation, and screenshot capture.
"""

import os
from pathlib import Path
from contextlib import contextmanager
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# Allow Django ORM operations inside Playwright's route event loop
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def create_django_route_handler(client):
    """Return a Playwright route callback that delegates requests directly to Django's test client."""
    static_dir = BASE_DIR / "static"

    def handler(route):
        req = route.request
        full_url = req.url
        # Extract path and query string
        if "127.0.0.1/" in full_url:
            path_and_query = "/" + full_url.split("127.0.0.1/", 1)[-1]
        elif "127.0.0.1" in full_url:
            path_and_query = "/"
        else:
            path_and_query = "/"

        path = path_and_query.split("?")[0]

        # Handle static files
        if path.startswith("/static/"):
            rel_path = path[len("/static/"):].split("?")[0]
            local_file = static_dir / rel_path
            if local_file.exists() and local_file.is_file():
                content = local_file.read_bytes()
                ext = local_file.suffix.lower()
                ct_map = {
                    ".js": "text/javascript",
                    ".css": "text/css",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".svg": "image/svg+xml",
                    ".json": "application/json",
                }
                ct = ct_map.get(ext, "application/octet-stream")
                route.fulfill(status=200, headers={"Content-Type": ct}, body=content)
                return
            route.fulfill(status=404, body=b"Static file not found")
            return

        # Delegate to Django test client
        method = req.method.upper()
        content_type = req.headers.get("content-type", "application/json")

        headers = {}
        for k, v in req.headers.items():
            k_lower = k.lower()
            if k_lower in ("content-type", "content-length"):
                continue
            headers[f"HTTP_{k.upper().replace('-', '_')}"] = v

        if method == "POST":
            post_body = req.post_data_buffer or b""
            if content_type.startswith("multipart/form-data"):
                resp = client.generic("POST", path_and_query, data=post_body, content_type=content_type, **headers)
            else:
                resp = client.post(path_and_query, data=post_body, content_type=content_type, **headers)
        elif method == "GET":
            resp = client.get(path_and_query, **headers)
        else:
            resp = client.generic(method, path_and_query, data=req.post_data_buffer or b"", content_type=content_type, **headers)

        resp_headers = {}
        for h_k, h_v in resp.headers.items():
            resp_headers[h_k] = str(h_v)

        from django.db import connection
        connection.close()

        route.fulfill(status=resp.status_code, headers=resp_headers, body=resp.content)

    return handler


@contextmanager
def launch_app(client, viewport=None, lang="en", fake_media=False, has_touch=True):
    """Context manager launching Chromium and serving the app in-memory to the page."""
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed. Install requirements-dev.txt to run e2e tests.")
    if viewport is None:
        viewport = {"width": 390, "height": 844}

    launch_args = []
    if fake_media:
        launch_args.extend([
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=launch_args)
        context = browser.new_context(
            viewport=viewport,
            user_agent="Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36",
            has_touch=has_touch,
            is_mobile=True,
        )
        page = context.new_page()

        # Pre-seed localStorage language
        page.add_init_script(f"""
            localStorage.setItem('kadai_khata_lang', '{lang}');
        """)

        # Intercept all 127.0.0.1 requests
        page.route("http://127.0.0.1/**", create_django_route_handler(client))

        page.goto("http://127.0.0.1/")
        page.wait_for_selector("#app-title", timeout=10000)

        try:
            yield page, browser
        finally:
            browser.close()
