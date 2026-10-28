"""Tests for eval_vision management command flags: --show-failures and --repeat N.

All tests run 100% offline using a fake/mock client (never calling the real Meta API).
"""

from io import StringIO
from unittest.mock import MagicMock, patch
import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_eval_vision_show_failures_flag_with_fake_client():
    """Verify eval_vision --show-failures prints detailed failure markings per image."""
    out = StringIO()

    # Run eval_vision in offline mock mode with --show-failures
    call_command("eval_vision", "--show-failures", stdout=out)
    output = out.getvalue()

    # Verify header and detailed failure breakdown
    assert "Evaluating Notebook Photo Digitizer" in output
    assert "Detailed Failure & Row Analysis" in output
    assert "Expected Rows (Ground Truth):" in output
    assert "Extracted Rows (Model Output):" in output

    # Check that failure and match categories are present
    assert any(tag in output for tag in ("[MATCHED EXACT]", "[WRONG AMOUNT]", "[MISSED ROW]", "[WRONG DIRECTION]"))
    assert "[EXTRACTED]" in output or "[FALSE ROW]" in output


@pytest.mark.django_db
def test_eval_vision_repeat_flag_with_fake_client():
    """Verify eval_vision --repeat 2 prints per-run lines and aggregate stats."""
    out = StringIO()

    # Run eval_vision in offline mock mode with --repeat 2
    call_command("eval_vision", "--repeat", "2", stdout=out)
    output = out.getvalue()

    # Verify per-run output lines
    assert "Run 1/2:" in output
    assert "Run 2/2:" in output

    # Verify aggregate statistics summary
    assert "=== Aggregate Summary Over 2 Runs ===" in output
    assert "Mean Recall:" in output
    assert "Mean Exact-Field Accuracy:" in output
    assert "Total False-Positive Rows:" in output
    assert "Min/Max Latency:" in output
