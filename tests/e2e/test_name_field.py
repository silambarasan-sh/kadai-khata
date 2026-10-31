"""E2E regression tests for Customer Name field on draft/confirm cards.

Verifies that on both text-parse and photo-review draft cards:
- Every draft card has a visible, non-empty, editable customer name input
- The name input has proper DOM properties (display: block, visibility: visible, opacity: 1, positive bounding box)
- Editing the customer name changes what is confirmed and saved to the ledger.
Tested under Pixel 5 (393x851) and 360x800 mobile viewports in English and Tamil.
"""

import pytest
from django.core.management import call_command
from ledger.models import Customer, LedgerEntry
from tests.e2e.e2e_helper import launch_app

pytestmark = [pytest.mark.e2e]


@pytest.fixture(autouse=True)
def setup_db(db):
    """Seed base demo customers for testing."""
    call_command("seed_demo_data")


@pytest.mark.parametrize(
    "viewport_name,viewport,lang",
    [
        ("pixel5_en", {"width": 393, "height": 851}, "en"),
        ("android360_ta", {"width": 360, "height": 800}, "ta"),
    ],
)
@pytest.mark.django_db(transaction=True)
def test_draft_card_customer_name_visible_and_editable_text_parse(client, viewport_name, viewport, lang):
    """Verify customer name input is visible, non-empty, and editing updates the confirmed customer."""
    with launch_app(client, viewport=viewport, lang=lang) as (page, browser):
        # Type a transaction sentence and submit
        sentence_input = page.locator("#sentence-input")
        sentence_input.fill("Ravi 450 udhaar paal packet")
        page.locator("#send-btn").click()

        # Wait for confirm view and draft cards
        page.wait_for_selector("#confirm-view", state="visible", timeout=10000)
        draft_cards = page.locator("#draft-cards-container .draft-card")
        assert draft_cards.count() > 0, "Expected at least one draft card to appear"

        card = draft_cards.first
        name_input = card.locator(".draft-form-group input.draft-input").first

        # Verify DOM properties and computed styles
        assert name_input.is_visible(), "Customer name input must be visible"
        val = name_input.input_value().strip()
        assert len(val) > 0, f"Customer name input value must be non-empty, got '{val}'"
        assert "ravi" in val.lower(), f"Expected parsed customer name 'Ravi', got '{val}'"

        box = name_input.bounding_box()
        assert box is not None, "Bounding box must be present"
        assert box["width"] > 180, f"Bounding box width {box['width']} is too small"
        assert box["height"] >= 32, f"Bounding box height {box['height']} is too small"

        # Check computed styles
        styles = name_input.evaluate("""el => {
            const cs = window.getComputedStyle(el);
            return {
                display: cs.display,
                visibility: cs.visibility,
                opacity: cs.opacity
            };
        }""")
        assert styles["display"] in ("block", "inline-block"), f"Unexpected display style: {styles['display']}"
        assert styles["visibility"] == "visible", f"Unexpected visibility: {styles['visibility']}"
        assert float(styles["opacity"]) >= 0.9, f"Unexpected opacity: {styles['opacity']}"

        # Edit customer name
        edited_name = "Ravi Supermarket Branch"
        name_input.fill(edited_name)
        assert name_input.input_value() == edited_name

        # Click Confirm on the card
        confirm_btn = card.locator(".btn-primary").first
        confirm_btn.click()

        # Verify confirmation toast and return to ledger
        page.wait_for_selector(".toast-success", timeout=6000)
        page.wait_for_selector("#home-view", state="visible", timeout=6000)

        # Verify confirmed customer exists in ledger database with edited name
        saved_customer = Customer.objects.filter(name=edited_name).first()
        assert saved_customer is not None, f"Expected customer '{edited_name}' to be saved in DB"
        entry = LedgerEntry.objects.filter(customer=saved_customer).first()
        assert entry is not None, f"Expected transaction entry for '{edited_name}'"
        assert float(entry.amount) == 450.0


@pytest.mark.django_db(transaction=True)
def test_draft_card_customer_name_visible_and_editable_photo_review(client):
    """Verify customer name inputs in photo review flow: Latin names, Tamil names, and new customers."""
    with launch_app(client, viewport={"width": 360, "height": 800}, lang="en") as (page, browser):
        # Click sample notebook button
        page.locator("#try-sample-notebook-btn").click()

        # Wait for review cards
        page.wait_for_selector("#confirm-view", state="visible", timeout=15000)
        draft_cards = page.locator("#draft-cards-container .draft-card")
        count = draft_cards.count()
        assert count > 0, "Photo review should have drafted rows"

        # Check every draft card's customer name input
        for idx in range(count):
            card = draft_cards.nth(idx)
            name_input = card.locator(".draft-form-group input.draft-input").first
            assert name_input.is_visible(), f"Card #{idx+1} name input must be visible"

            val = name_input.input_value().strip()
            assert len(val) > 0, f"Card #{idx+1} name input must have non-empty value, got '{val}'"

            box = name_input.bounding_box()
            assert box is not None
            assert box["width"] > 160
            assert box["height"] >= 30

        # Edit first card and confirm
        first_card = draft_cards.first
        first_name_input = first_card.locator(".draft-form-group input.draft-input").first
        special_name = "Kavitha New Customer"
        first_name_input.fill(special_name)

        first_confirm_btn = first_card.locator(".btn-primary").first
        first_confirm_btn.click()

        page.wait_for_selector(".toast-success", timeout=6000)

        # Verify DB entry recorded with edited special_name
        assert Customer.objects.filter(name=special_name).exists(), f"Customer '{special_name}' must exist in DB"
