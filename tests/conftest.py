"""Pytest configuration and global fixtures."""

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def force_mock_meta_mode(monkeypatch):
    """Ensure tests never call the real Meta Model API regardless of local .env settings."""
    monkeypatch.setattr(settings, "META_MODE", "mock")
