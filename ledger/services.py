"""Core ledger business logic and service functions.

Handles customer resolution, balance aggregation, and validation of amounts.
Does not contain any AI logic - pure deterministic service layer.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple, Union
from django.conf import settings
from django.db import models
from django.db.models import Count, DecimalField, F, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Customer, EntryKind, LedgerEntry


class LedgerValidationError(ValueError):
    """Raised when an entry amount or payload fails business rules."""
    pass


def validate_and_normalize_amount(amount: Union[Decimal, int, float, str]) -> Decimal:
    """Validate that amount is positive, within limits, and convert to 2 decimal places."""
    try:
        if isinstance(amount, (int, float)):
            dec = Decimal(str(amount))
        elif isinstance(amount, str):
            dec = Decimal(amount.strip())
        elif isinstance(amount, Decimal):
            dec = amount
        else:
            raise LedgerValidationError(f"Unsupported amount type: {type(amount).__name__}")
    except (InvalidOperation, TypeError) as exc:
        raise LedgerValidationError(f"Invalid number format for amount: {amount}") from exc

    if dec.is_nan() or dec.is_infinite():
        raise LedgerValidationError("Amount cannot be NaN or Infinite.")

    # Quantize to standard Indian currency paise (2 decimal places)
    dec = dec.quantize(Decimal("0.01"))

    if dec <= Decimal("0.00"):
        raise LedgerValidationError("Amount must be strictly greater than zero.")

    max_amount = getattr(settings, "MAX_ENTRY_AMOUNT", Decimal("100000.00"))
    if dec > max_amount:
        raise LedgerValidationError(
            f"Amount ₹{dec} exceeds maximum allowed limit of ₹{max_amount}."
        )

    return dec


def add_entry(
    customer_name: str,
    kind: Union[str, EntryKind],
    amount: Union[Decimal, int, float, str],
    note: str = "",
    source_text: str = "",
    created_at: Optional[timezone.datetime] = None,
) -> LedgerEntry:
    """Find or create customer (case-insensitive) and record a ledger entry.

    Args:
        customer_name: Customer's name (matched case-insensitively).
        kind: 'credit_given' or 'payment_received'.
        amount: Transaction amount (> 0 and <= MAX_ENTRY_AMOUNT).
        note: Human-readable note or item breakdown.
        source_text: Raw voice/text transcribed input that initiated this.
        created_at: Optional specific timestamp (useful for backdated seed data).

    Returns:
        The newly saved LedgerEntry instance.

    Raises:
        LedgerValidationError: If customer name is empty, kind is invalid, or amount is out of bounds.
    """
    clean_name = (customer_name or "").strip()
    if not clean_name:
        raise LedgerValidationError("Customer name cannot be empty.")

    valid_kinds = {EntryKind.CREDIT_GIVEN.value, EntryKind.PAYMENT_RECEIVED.value}
    kind_str = str(kind.value if isinstance(kind, EntryKind) else kind).strip().lower()
    if kind_str not in valid_kinds:
        raise LedgerValidationError(
            f"Invalid kind '{kind}'. Expected one of: {sorted(list(valid_kinds))}"
        )

    validated_amount = validate_and_normalize_amount(amount)

    # Case-insensitive find or create
    customer = Customer.objects.filter(name__iexact=clean_name).first()
    if not customer:
        customer = Customer.objects.create(name=clean_name)

    entry_kwargs = {
        "customer": customer,
        "kind": kind_str,
        "amount": validated_amount,
        "note": (note or "").strip(),
        "source_text": (source_text or "").strip(),
    }
    if created_at is not None:
        entry_kwargs["created_at"] = created_at

    return LedgerEntry.objects.create(**entry_kwargs)


def get_balance(customer: Customer) -> Decimal:
    """Calculate the net outstanding balance for a customer.

    Balance = Total Credit Given (Udhaar) - Total Payment Received.
    - Positive: Customer owes money to the shopkeeper.
    - Zero: Fully settled.
    - Negative: Customer has an advance balance with the shopkeeper.
    """
    agg = customer.entries.aggregate(
        total_credit=Coalesce(
            Sum("amount", filter=Q(kind=EntryKind.CREDIT_GIVEN)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        total_paid=Coalesce(
            Sum("amount", filter=Q(kind=EntryKind.PAYMENT_RECEIVED)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    )
    balance = (agg["total_credit"] - agg["total_paid"]).quantize(Decimal("0.01"))
    return balance


def list_customers_with_balance():
    """Return all customers annotated with total_credit, total_paid, balance, and last_entry_at."""
    return (
        Customer.objects.annotate(
            total_credit=Coalesce(
                Sum("entries__amount", filter=Q(entries__kind=EntryKind.CREDIT_GIVEN)),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            total_paid=Coalesce(
                Sum("entries__amount", filter=Q(entries__kind=EntryKind.PAYMENT_RECEIVED)),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            last_entry_at=Max("entries__created_at"),
            entry_count=Count("entries"),
        )
        .annotate(
            balance=F("total_credit") - F("total_paid")
        )
        .order_by("-balance", "name")
    )


def reverse_entry(entry_id: int, reason: str = "") -> Tuple[LedgerEntry, Decimal]:
    """Create an offsetting ledger entry linked to the original entry (audit trail).

    Rules:
    - Never deletes records.
    - If entry is already a reversal (is_reversal=True), raises LedgerValidationError.
    - If entry has already been reversed (reversal_records.exists()), raises LedgerValidationError.
    - Offsetting entry inverts the kind:
      credit_given -> payment_received
      payment_received -> credit_given
    - Offsetting entry sets is_reversal=True and reversed_entry=original.
    - Note captures citation of original entry ID and optional reason.
    - Returns (reversal_entry, new_balance).
    """
    try:
        original = LedgerEntry.objects.select_related("customer").get(id=entry_id)
    except (LedgerEntry.DoesNotExist, ValueError) as exc:
        raise LedgerValidationError(f"Ledger entry #{entry_id} not found.") from exc

    if original.is_reversal:
        raise LedgerValidationError(
            f"Entry #{entry_id} is already a reversal entry and cannot be reversed again."
        )

    if original.reversal_records.exists():
        existing_rev = original.reversal_records.first()
        raise LedgerValidationError(
            f"Entry #{entry_id} was already reversed by entry #{existing_rev.id}."
        )

    # Invert kind
    if original.kind == EntryKind.CREDIT_GIVEN:
        rev_kind = EntryKind.PAYMENT_RECEIVED
    else:
        rev_kind = EntryKind.CREDIT_GIVEN

    clean_reason = (reason or "").strip()
    rev_note = f"Reversal of #{original.id}"
    if clean_reason:
        rev_note = f"{rev_note}: {clean_reason}"
    elif original.note:
        rev_note = f"{rev_note} (original: {original.note})"

    reversal_entry = LedgerEntry.objects.create(
        customer=original.customer,
        kind=rev_kind,
        amount=original.amount,
        note=rev_note,
        source_text=f"Reversal of #{original.id}",
        is_reversal=True,
        reversed_entry=original,
    )

    new_balance = get_balance(original.customer)
    return reversal_entry, new_balance


def get_customer_timeline(customer_id: int) -> dict:
    """Fetch chronological entries for a customer with computed running balances."""
    try:
        customer = Customer.objects.get(id=customer_id)
    except (Customer.DoesNotExist, ValueError) as exc:
        raise LedgerValidationError(f"Customer #{customer_id} not found.") from exc

    current_balance = get_balance(customer)
    # Fetch entries ordered by created_at ascending, then id ascending to compute running balance
    entries_asc = (
        customer.entries.select_related("reversed_entry")
        .prefetch_related("reversal_records")
        .order_by("created_at", "id")
    )

    running = Decimal("0.00")
    items = []
    last_entry_at = None

    for e in entries_asc:
        last_entry_at = e.created_at
        if e.kind == EntryKind.CREDIT_GIVEN:
            running += e.amount
        else:
            running -= e.amount

        has_been_reversed = e.reversal_records.exists()
        reversal_id = e.reversal_records.first().id if has_been_reversed else None

        items.append({
            "id": e.id,
            "kind": e.kind,
            "kind_display": e.get_kind_display(),
            "amount": f"{e.amount:.2f}",
            "note": e.note,
            "source_text": e.source_text,
            "created_at": e.created_at.isoformat(),
            "is_reversal": e.is_reversal,
            "reversed_entry_id": e.reversed_entry_id,
            "has_been_reversed": has_been_reversed,
            "reversal_id": reversal_id,
            "running_balance": f"{running:.2f}",
        })

    # Order newest first for timeline display
    items.reverse()

    # Calculate days since last entry & aging bucket
    days_since_last = 0
    if last_entry_at:
        days_since_last = max(0, (timezone.now() - last_entry_at).days)

    if days_since_last <= 30:
        aging_bucket = "0-30"
    elif days_since_last <= 60:
        aging_bucket = "31-60"
    else:
        aging_bucket = "60+"

    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "balance": f"{current_balance:.2f}",
            "days_since_last_entry": days_since_last,
            "aging_bucket": aging_bucket,
        },
        "entries": items,
    }

