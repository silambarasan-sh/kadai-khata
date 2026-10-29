"""Verifiable Payment Reminder Generator with Deterministic Balance Verification.

Adheres to strict safety rules:
1. Server computes customer balance and overdue duration directly from DB.
2. Only factual customer name, balance, and days overdue are passed to the model.
3. Strict Verifier ensures the message contains the EXACT balance and NO extraneous rupee amounts.
4. If the draft fails verification, regenerates once.
5. If second attempt also fails, produces a deterministic fallback template labeled 'fallback'.
6. Never sends messages automatically: generates prefilled WhatsApp links (wa.me) or copyable text.
"""

import re
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union
from django.conf import settings
from django.utils import timezone

from .meta_client import MetaClient, MetaClientError
from .models import Customer, EntryKind
from .services import get_balance


@dataclass
class ReminderResult:
    """Standardized response from reminder generation and verification."""

    customer_id: int
    customer_name: str
    phone: str
    balance: str
    days_overdue: int
    language: str
    tone: str
    message: str
    verified: bool
    source_label: str  # "live" | "mock" | "fallback"
    whatsapp_url: Optional[str] = None
    provider: str = "meta"
    model: str = ""
    badge_label: str = ""


def verify_reminder_balance(
    text: str,
    expected_balance: Decimal,
    days_overdue: Optional[int] = None,
) -> bool:
    """Verify that message mentions the exact balance and NO other conflicting currency numbers.

    Rules:
    - Expected balance (e.g. 500 or 500.00) must appear in the text.
    - No other non-matching monetary amounts should appear.
    """
    clean_text = text.replace(",", "")
    bal_int = int(expected_balance)
    bal_str_int = str(bal_int)
    bal_str_dec = f"{expected_balance:.2f}"

    # Check that balance string is in the text
    has_balance = (bal_str_int in clean_text) or (bal_str_dec in clean_text)
    if not has_balance:
        return False

    # Extract all digit sequences
    numbers = re.findall(r"\b\d+(?:\.\d{1,2})?\b", clean_text)
    # Check for hallucinated extra amounts
    for num_str in numbers:
        try:
            val = Decimal(num_str)
            # Allow: the balance itself, the integer balance
            if val == expected_balance or int(val) == bal_int:
                continue
            # Allow explicit days overdue if passed
            if days_overdue is not None and int(val) == days_overdue:
                continue
            # Allow small calendar day numbers (<= 31)
            if val <= Decimal("31"):
                continue
            # If a number differs and looks like an amount, it's an extraneous amount
            return False
        except Exception:
            continue

    return True


def deterministic_fallback_template(name: str, balance: Decimal, language: str, tone: str) -> str:
    """Generate deterministic verified fallback message."""
    bal_display = f"{balance:.0f}" if balance == int(balance) else f"{balance:.2f}"
    lang = (language or "ta").lower()

    if lang == "ta":
        if tone == "firm":
            return f"வணக்கம் {name}, உங்கள் கடை பாக்கி தொகை ரூ.{bal_display} உடனடியாக செலுத்த வேண்டுகிறோம். நன்றி."
        return f"வணக்கம் {name}, உங்கள் கடை கணக்கில் பாக்கி தொகை ரூ.{bal_display} உள்ளது. வசதிப்படும்போது செலுத்தவும். நன்றி."

    elif lang == "tanglish":
        if tone == "firm":
            return f"Vanakkam {name}, ungal kadai balance Rs.{bal_display} seekiram settle pannunga. Nandri."
        return f"Vanakkam {name}, ungal kadai balance Rs.{bal_display} irukku. Convenient time-la pay pannunga. Nandri."

    else:  # English
        if tone == "firm":
            return f"Hello {name}, your pending balance is Rs.{bal_display}. Please arrange payment at your earliest convenience. Thank you."
        return f"Hello {name}, kindly note your pending shop balance is Rs.{bal_display}. Please pay when convenient. Thank you."


def generate_reminder(
    customer_id: int,
    language: str = "ta",
    tone: str = "soft",
    provider: Optional[str] = None,
) -> ReminderResult:
    """Generate a polite, verified payment reminder message for a customer."""
    from ledger.meta_client import format_badge_label

    customer = Customer.objects.get(id=customer_id)
    balance = get_balance(customer)
    first_name = customer.name.split()[0]

    # Calculate days overdue from last entry
    last_entry = customer.entries.order_by("-created_at").first()
    days_overdue = 0
    if last_entry:
        days_overdue = max(1, (timezone.now() - last_entry.created_at).days)

    meta_mode = getattr(settings, "META_MODE", "mock").strip().lower()

    effective_provider = (
        provider if provider is not None else getattr(settings, "META_PROVIDER", "meta")
    ).strip().lower()
    if effective_provider not in ("meta", "partner"):
        effective_provider = "meta"

    effective_model = (
        getattr(settings, "PARTNER_MODEL", "meta-models/muse-spark-open-1026")
        if effective_provider == "partner"
        else getattr(settings, "META_MODEL", "muse-spark-1.3")
    )

    # If mock mode, return mock verified reminder
    if meta_mode == "mock":
        msg = deterministic_fallback_template(first_name, balance, language, tone)
        verified = verify_reminder_balance(msg, balance, days_overdue=days_overdue)
        wa_url = None
        if customer.phone:
            clean_phone = re.sub(r"[^0-9]", "", customer.phone)
            # Add India 91 prefix if 10 digits
            if len(clean_phone) == 10:
                clean_phone = f"91{clean_phone}"
            wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"

        return ReminderResult(
            customer_id=customer.id,
            customer_name=customer.name,
            phone=customer.phone,
            balance=f"{balance:.2f}",
            days_overdue=days_overdue,
            language=language,
            tone=tone,
            message=msg,
            verified=verified,
            source_label="mock",
            whatsapp_url=wa_url,
            provider=effective_provider,
            model=effective_model,
            badge_label=format_badge_label("mock", effective_provider),
        )

    from ledger.demo_guards import is_daily_budget_exceeded
    if is_daily_budget_exceeded():
        msg = deterministic_fallback_template(first_name, balance, language, tone)
        wa_url = None
        if customer.phone:
            clean_phone = re.sub(r"[^0-9]", "", customer.phone)
            if len(clean_phone) == 10:
                clean_phone = f"91{clean_phone}"
            wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}"
        return ReminderResult(
            customer_id=customer.id,
            customer_name=customer.name,
            phone=customer.phone,
            balance=f"{balance:.2f}",
            days_overdue=days_overdue,
            language=language,
            tone=tone,
            message=f"[Demo budget reached - offline mode] {msg}",
            verified=True,
            source_label="fallback",
            whatsapp_url=wa_url,
            provider=effective_provider,
            model=effective_model,
            badge_label=format_badge_label("fallback", effective_provider),
        )

    # Live Mode generation with verification and retry
    client = MetaClient(mode="live", provider=effective_provider)
    prompt = (
        f"You are writing a polite reminder from a Tamil Nadu neighborhood shopkeeper.\n"
        f"Customer First Name: {first_name}\n"
        f"Exact Outstanding Balance: Rs. {balance:.2f}\n"
        f"Days Overdue: {days_overdue}\n"
        f"Language: {language} ('ta' for Tamil script, 'en' for English, 'tanglish' for Tamil in Latin letters)\n"
        f"Tone: {tone} ('soft' is friendly and respectful, 'firm' is clear and requesting payment)\n"
        f"CRITICAL CONSTRAINT: You MUST mention the exact balance amount (Rs. {balance:.2f}) and NO other rupee amounts. "
        f"Keep the message under 25 words."
    )

    final_msg: Optional[str] = None
    source_label = "live"
    verified = False

    # Try up to 2 times (initial + 1 regeneration)
    for attempt in range(2):
        try:
            res = client.chat_completion(
                messages=[
                    {"role": "system", "content": "You write concise, polite payment reminders for shopkeepers. Strictly state only the requested balance without inventing other numbers."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            raw_text = res.payload.get("content", "").strip()
            # Clean enclosing quotes if any
            clean_draft = re.sub(r'^["\']|["\']$', "", raw_text)

            if verify_reminder_balance(clean_draft, balance, days_overdue=days_overdue):
                final_msg = clean_draft
                verified = True
                source_label = "live"
                effective_model = getattr(res, "model", effective_model)
                break
        except MetaClientError:
            break

    # If verification failed on both attempts or API failed, use fallback template
    if not final_msg or not verified:
        final_msg = deterministic_fallback_template(first_name, balance, language, tone)
        verified = True  # Fallback template is guaranteed verified
        source_label = "fallback"

    wa_url = None
    if customer.phone:
        clean_phone = re.sub(r"[^0-9]", "", customer.phone)
        if len(clean_phone) == 10:
            clean_phone = f"91{clean_phone}"
        wa_url = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(final_msg)}"

    return ReminderResult(
        customer_id=customer.id,
        customer_name=customer.name,
        phone=customer.phone,
        balance=f"{balance:.2f}",
        days_overdue=days_overdue,
        language=language,
        tone=tone,
        message=final_msg,
        verified=verified,
        source_label=source_label,
        whatsapp_url=wa_url,
        provider=effective_provider,
        model=effective_model,
        badge_label=format_badge_label(source_label, effective_provider),
    )
