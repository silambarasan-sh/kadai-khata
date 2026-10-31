"""Pytest configuration and global fixtures."""

import os
import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def force_mock_meta_mode(monkeypatch):
    """Ensure tests never call the real Meta Model API regardless of local .env settings."""
    monkeypatch.setattr(settings, "META_MODE", "mock")


@pytest.fixture(autouse=True)
def configure_test_allowed_hosts(settings):
    """Ensure test hostnames are allowed during tests without modifying production settings."""
    hosts = list(settings.ALLOWED_HOSTS)
    for h in ("testserver", "127.0.0.1", "localhost"):
        if h not in hosts:
            hosts.append(h)
    settings.ALLOWED_HOSTS = hosts


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end browser tests requiring Playwright and Chromium")


def pytest_ignore_collect(*args, **kwargs):
    """Skip collecting e2e tests unless RUN_E2E=1 and playwright is available."""
    path_str = str(args[0]) if args else ""
    if "e2e" in path_str:
        if os.environ.get("RUN_E2E") != "1":
            return True
        try:
            import playwright  # noqa: F401
        except ImportError:
            return True
    return False


def pytest_runtest_setup(item):
    """Enforce that e2e marked tests are skipped unless RUN_E2E=1."""
    if "e2e" in item.keywords or "e2e" in str(item.fspath):
        if os.environ.get("RUN_E2E") != "1":
            pytest.skip("E2E tests skipped because RUN_E2E=1 is not set")
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest.skip("E2E tests skipped because playwright is not installed")
