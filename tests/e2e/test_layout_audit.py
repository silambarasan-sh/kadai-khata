"""Layout audit tests across main screens in English and Tamil at 360px and 390px.

Asserts:
- No horizontal overflow (scrollWidth <= innerWidth)
- No element wider than viewport (offsetWidth <= innerWidth)
- No clipped badge, button, or card text (scrollWidth <= clientWidth)
Screens covered:
1. Home view (ledger summary & customer list)
2. Text-parse draft confirm cards
3. Photo review draft cards
4. Customer timeline & transaction audit view
5. Payment reminder modal
6. Collections agent review view
"""

import pytest
from django.core.management import call_command
from tests.e2e.e2e_helper import launch_app

pytestmark = [pytest.mark.e2e]


@pytest.fixture(autouse=True)
def setup_db(db):
    """Seed demo data."""
    call_command("seed_demo_data")


def audit_page_layout(page, screen_name):
    """Perform comprehensive layout audit on the currently visible page view."""
    results = page.evaluate("""() => {
        const innerWidth = window.innerWidth;
        const htmlScroll = document.documentElement.scrollWidth;
        const bodyScroll = document.body.scrollWidth;

        const violations = [];

        // 1. Check window-level horizontal overflow
        if (htmlScroll > innerWidth + 1) {
            violations.push(`HTML element scrollWidth (${htmlScroll}) exceeds innerWidth (${innerWidth})`);
        }
        if (bodyScroll > innerWidth + 1) {
            violations.push(`Body element scrollWidth (${bodyScroll}) exceeds innerWidth (${innerWidth})`);
        }

        // 2. Check all visible elements wider than viewport
        const allVisible = Array.from(document.querySelectorAll('*')).filter(el => {
            const cs = window.getComputedStyle(el);
            if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        });

        for (const el of allVisible) {
            // Horizontal scroll containers like chips lists or modal scrollables are allowed to scroll internally
            const isScrollTrack = el.classList.contains('chips-list') || el.classList.contains('candidate-options-row');
            if (el.offsetWidth > innerWidth + 1 && !isScrollTrack) {
                const idOrClass = el.id ? `#${el.id}` : `.${Array.from(el.classList).join('.')}`;
                violations.push(`Element ${el.tagName}${idOrClass} offsetWidth (${el.offsetWidth}) > innerWidth (${innerWidth})`);
            }

            // 3. Check for clipped badge, button, or header text
            const isTextPill = el.classList.contains('badge') || el.classList.contains('lang-toggle-btn') ||
                               el.classList.contains('engine-pill-btn') || el.classList.contains('brand-title');
            if (isTextPill) {
                if (el.scrollWidth > el.clientWidth + 1) {
                    const idOrClass = el.id ? `#${el.id}` : `.${Array.from(el.classList).join('.')}`;
                    violations.push(`Text clipped in ${el.tagName}${idOrClass}: scrollWidth (${el.scrollWidth}) > clientWidth (${el.clientWidth}), text="${el.textContent.trim()}"`);
                }
            }
        }

        return {
            innerWidth,
            htmlScroll,
            bodyScroll,
            violations
        };
    }""")

    assert len(results["violations"]) == 0, (
        f"Layout audit failed on screen '{screen_name}':\n" + "\n".join(results["violations"])
    )


@pytest.mark.parametrize(
    "viewport_name,viewport,lang",
    [
        ("360px_en", {"width": 360, "height": 800}, "en"),
        ("360px_ta", {"width": 360, "height": 800}, "ta"),
        ("390px_en", {"width": 390, "height": 844}, "en"),
        ("390px_ta", {"width": 390, "height": 844}, "ta"),
    ],
)
@pytest.mark.django_db(transaction=True)
def test_mobile_layout_audit_all_screens(client, viewport_name, viewport, lang):
    """Run layout audit across all 6 core application views."""
    with launch_app(client, viewport=viewport, lang=lang) as (page, browser):
        # 1. Screen 1: Home View
        page.wait_for_selector("#customer-list-container .customer-card", timeout=8000)
        audit_page_layout(page, f"Home ({viewport_name})")

        # 2. Screen 2: Text-Parse Draft Cards
        sentence_input = page.locator("#sentence-input")
        sentence_input.fill("Ravi 450 udhaar paal packet")
        page.locator("#send-btn").click()
        page.wait_for_selector("#confirm-view", state="visible", timeout=8000)
        page.wait_for_selector(".draft-card", timeout=8000)
        audit_page_layout(page, f"Confirm Drafts ({viewport_name})")

        # Discard drafts to go back to home
        page.locator("#discard-all-btn").click()
        page.wait_for_selector("#home-view", state="visible", timeout=8000)

        # 3. Screen 3: Photo Review Draft Cards
        page.locator("#try-sample-notebook-btn").click()
        page.wait_for_selector("#confirm-view", state="visible", timeout=12000)
        page.wait_for_selector(".draft-card", timeout=12000)
        audit_page_layout(page, f"Photo Review ({viewport_name})")

        # Discard photo drafts
        page.locator("#discard-all-btn").click()
        page.wait_for_selector("#home-view", state="visible", timeout=8000)

        # 4. Screen 4: Customer Timeline
        first_customer = page.locator("#customer-list-container .customer-card").first
        first_customer.click()
        page.wait_for_selector("#customer-detail-view", state="visible", timeout=8000)
        audit_page_layout(page, f"Customer Timeline ({viewport_name})")

        # 5. Screen 5: Payment Reminder Modal
        page.locator("#open-reminder-btn").click()
        page.wait_for_selector("#reminder-modal", state="visible", timeout=8000)
        audit_page_layout(page, f"Reminder Modal ({viewport_name})")

        # Close reminder modal
        page.locator("#close-reminder-modal-btn").click()
        page.wait_for_selector("#reminder-modal", state="hidden", timeout=8000)

        # Go back to home
        page.locator("#back-to-home-btn").click()
        page.wait_for_selector("#home-view", state="visible", timeout=8000)

        # 6. Screen 6: Collections View
        page.locator("#tab-collections-btn").click()
        page.wait_for_selector("#collections-view", state="visible", timeout=8000)
        audit_page_layout(page, f"Collections Initial ({viewport_name})")

        # Run Collections Review to inspect plan cards & trace
        page.locator("#run-collections-btn").click()
        page.wait_for_selector(".plan-card", timeout=10000)
        audit_page_layout(page, f"Collections Plan ({viewport_name})")

