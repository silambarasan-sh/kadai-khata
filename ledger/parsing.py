"""Core AI Parsing and Draft Confirmation Workflow for Kadai Khata.

Translates Tanglish voice/text input into structured DraftEntry models via:
1. Meta Model API tool calling (live mode)
2. Deterministic mock parser (mock mode)
3. Rule-based regex parser (fallback mode)

CRITICAL RULE: DraftEntry objects are NEVER saved to the official ledger until
explicitly confirmed by the shop owner via confirm().
"""

import difflib
import json
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union
from django.conf import settings
from django.utils import timezone

from .meta_client import MetaClient, MetaClientError
from .models import Customer, DraftEntry, DraftStatus, EntryKind, LedgerEntry, SourceLabel
from .prompts import LEDGER_TOOLS, build_system_prompt
from .services import LedgerValidationError, add_entry, get_balance, validate_and_normalize_amount


class ParsingError(ValueError):
    """Raised when parsing input is invalid, rejected, or cannot be processed."""
    pass


@dataclass
class ParseResult:
    """Container for the output of parsing a Tanglish sentence."""

    batch_id: uuid.UUID
    drafts: List[DraftEntry]
    clarification: Optional[str] = None
    source_label: str = "mock"  # "live" | "mock" | "fallback"
    latency_ms: float = 0.0
    usage_tokens: Dict[str, int] = field(default_factory=dict)
    raw_text: str = ""


# Tamil number word conversions
TAMIL_NUMBER_MAP = {
    "ondraayiram": 1500,
    "oru ayiram aanju nooru": 1500,
    "oru ayiram ainooru": 1500,
    "rendayiram": 2000,
    "ayiram": 1000,
    "thollayiram": 900,
    "ennooru": 800,
    "ezhanooru": 700,
    "aanooru": 600,
    "aanju nooru": 500,
    "ainooru": 500,
    "naanooru": 400,
    "munnooru": 300,
    "irunooru": 200,
    "nooru": 100,
    "ambadhu": 50,
}


def find_matching_customer(raw_name: str) -> Tuple[Optional[Customer], Optional[str]]:
    """Match raw_name against existing customers.

    Returns:
        (exact_match_customer, suggested_match_name)
    """
    clean = raw_name.strip()
    if not clean:
        return None, None

    # 1. Exact case-insensitive match
    exact = Customer.objects.filter(name__iexact=clean).first()
    if exact:
        return exact, None

    # 2. Conservative fuzzy match suggestion (cutoff >= 0.85)
    all_names = list(Customer.objects.values_list("name", flat=True))
    matches = difflib.get_close_matches(clean, all_names, n=1, cutoff=0.85)
    if matches:
        suggested = matches[0]
        # Return suggested name for shopkeeper approval
        return None, suggested

    return None, None


def rule_based_fallback_parser(text: str, source_label: str = "fallback") -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Small deterministic regex/keyword parser used when offline or as a fallback."""
    clean_text = text.strip()
    if not clean_text:
        return [], "Empty input text."

    # Prompt injection or chatter check
    lower_text = clean_text.lower()
    if any(phrase in lower_text for phrase in ["ignore previous", "delete everything", "system prompt", "drop table", "admin access"]):
        return [], "Clarification: The input looks like a system command, not a valid customer transaction."

    if lower_text in ["hi", "hello", "vanakkam", "kaalai vanakkam", "test"]:
        return [], "Vanakkam! Ungal kadai udhaar transactions sollunga (e.g. 'Ravi 500 udhaar')."

    # Split compound clauses on comma or 'and' or 'aprom'
    clauses = re.split(r",|\baprom\b|\band\b", clean_text)
    extracted_entries: List[Dict[str, Any]] = []

    for clause in clauses:
        c_text = clause.strip()
        if not c_text:
            continue

        c_lower = c_text.lower()

        # Check direction
        is_credit = any(
            kw in c_lower
            for kw in ["udhaar", "kuduthen", "kuduthaen", "kadan", "potrukkaen", "eludhiko"]
        )
        is_payment = any(
            kw in c_lower
            for kw in [
                "kuduthanga", "kuduthaanga", "kuduthaar", "kuduthar", "kuduthaan", "kuduthan",
                "thirumba", "panam vanthathu", "settle", "clear", "gpay", "phonepe", "paytm",
                "pay", "vaangiten", "vaangunen", "anupunaan", "anupitaar", "anupinaar", "vanthuchu"
            ]
        )

        # Extract amount (digits or Tamil words)
        found_amount: Optional[Decimal] = None
        for word, val in TAMIL_NUMBER_MAP.items():
            if word in c_lower:
                found_amount = Decimal(str(val)).quantize(Decimal("0.01"))
                break

        if found_amount is None:
            num_match = re.search(r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)\s*(?:rupees|rooba|rs|/-)?", c_lower)
            if num_match:
                found_amount = Decimal(num_match.group(1)).quantize(Decimal("0.01"))

        # Extract customer name: check existing database customers with word boundary
        found_name: Optional[str] = None
        for cust in Customer.objects.all():
            if re.search(rf"\b{re.escape(cust.name.lower())}\b", c_lower):
                found_name = cust.name
                break

        if not found_name:
            skip_words = {
                "rupees", "rooba", "rs", "inr", "udhaar", "kuduthen", "kuduthaen", "kuduthaan",
                "kuduthan", "kuduthaar", "kuduthar", "kuduthaanga", "kuduthanga", "thirumba",
                "panam", "vanthathu", "settle", "clear", "gpay", "phonepe", "paytm", "pay",
                "pannaan", "pannitaar", "pannitaanga", "vaangiten", "vaangunen", "groceries",
                "provisions", "items", "cash", "la", "anupunaan", "anupitaar", "anupinaar",
                "vanthuchu", "kadan", "potrukkaen", "eludhiko", "bhai", "akka", "paatti",
                "annachi", "monthly", "balance", "arisi", "pooja", "samaiyal", "chai", "tea"
            }
            cleaned_words = []
            for token in c_text.split():
                clean_tok = re.sub(r"[^A-Za-z0-9-]", "", token)
                low_tok = clean_tok.lower()
                if low_tok.endswith("-ku"):
                    clean_tok = clean_tok[:-3]
                elif low_tok.endswith("ku") and len(clean_tok) > 3:
                    clean_tok = clean_tok[:-2]

                clean_alphanumeric = re.sub(r"[^A-Za-z0-9]", "", clean_tok)
                if not clean_alphanumeric or clean_alphanumeric.lower() in skip_words or clean_alphanumeric.isdigit():
                    continue
                cleaned_words.append(clean_alphanumeric)

            if cleaned_words:
                found_name = " ".join(cleaned_words)

        # Validate findings
        if found_name and found_amount:
            kind = "credit_given" if is_credit else ("payment_received" if is_payment else "credit_given")
            extracted_entries.append({
                "customer_name": found_name,
                "kind": kind,
                "amount": found_amount,
                "note": c_text,
            })
        elif not found_name and found_amount:
            return extracted_entries, f"Yaaruku {found_amount} udhaar/panam? Customer name sollunga."
        elif found_name and not found_amount:
            return extracted_entries, f"{found_name}-ku evlo rooba transaction? Amount sollunga."

    if not extracted_entries:
        return [], "Customer name matrum amount puriyavillai. Example: 'Ravi 500 udhaar kuduthen'."

    return extracted_entries, None


def parse_text(text: str) -> ParseResult:
    """Parse a Tanglish sentence into pending DraftEntry records.

    Workflow:
    1. Validates input bounds.
    2. Uses Meta Model API via MetaClient (or mock/fallback).
    3. Resolves existing customer matches / suggests fuzzy matches.
    4. Saves DraftEntry rows with status='pending'.

    Returns ParseResult container.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        raise ParsingError("Input text cannot be empty.")

    max_len = getattr(settings, "MAX_INPUT_TEXT_LENGTH", 500)
    if len(clean_text) > max_len:
        raise ParsingError(f"Input text exceeds maximum allowed length of {max_len} characters.")

    batch_id = uuid.uuid4()
    existing_customers = list(Customer.objects.values_list("name", flat=True))

    meta_mode = getattr(settings, "META_MODE", "mock").strip().lower()

    # Step 1: Execute Meta Client or Fallback
    draft_specs: List[Dict[str, Any]] = []
    clarification: Optional[str] = None
    source_label = meta_mode
    latency_ms = 0.0
    usage_tokens: Dict[str, int] = {}

    if meta_mode == "mock":
        # Deterministic mock parsing
        specs, clar = rule_based_fallback_parser(clean_text, source_label="mock")
        draft_specs = specs
        clarification = clar
        source_label = "mock"
        latency_ms = 2.5
        usage_tokens = {"prompt_tokens": len(clean_text.split()), "completion_tokens": 15, "total_tokens": len(clean_text.split()) + 15}

    else:
        # Live Meta AI call
        client = MetaClient(mode="live")
        sys_prompt = build_system_prompt(existing_customer_names=existing_customers)
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": clean_text},
        ]

        try:
            meta_res = client.chat_completion(
                messages=messages,
                tools=LEDGER_TOOLS,
                tool_choice="auto",
                temperature=0.0,
            )
            latency_ms = meta_res.latency_ms
            usage_tokens = meta_res.usage_tokens
            source_label = "live"

            # Parse tool calls from Meta response
            raw_tool_calls = meta_res.payload.get("tool_calls") or []

            if not raw_tool_calls:
                # No tool calls made by the model -> fall back to rule-based parser
                specs, clar = rule_based_fallback_parser(clean_text, source_label="fallback")
                draft_specs = specs
                clarification = clar
                source_label = "fallback"
            else:
                for call in raw_tool_calls:
                    fn_name = (
                        getattr(getattr(call, "function", None), "name", None)
                        or (call.get("function", {}).get("name") if isinstance(call, dict) else "")
                    )
                    fn_args_raw = (
                        getattr(getattr(call, "function", None), "arguments", None)
                        or (call.get("function", {}).get("arguments") if isinstance(call, dict) else "{}")
                    )

                    try:
                        args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except Exception:
                        args = {}

                    if fn_name == "record_ledger_entry":
                        cust_name = str(args.get("customer_name", "")).strip()
                        kind = str(args.get("kind", "")).strip().lower()
                        amount_val = args.get("amount")
                        note = str(args.get("note", "")).strip()

                        # Schema validation
                        if cust_name and kind in [EntryKind.CREDIT_GIVEN.value, EntryKind.PAYMENT_RECEIVED.value] and amount_val is not None:
                            try:
                                valid_amt = validate_and_normalize_amount(amount_val)
                                draft_specs.append({
                                    "customer_name": cust_name,
                                    "kind": kind,
                                    "amount": valid_amt,
                                    "note": note,
                                })
                            except LedgerValidationError:
                                pass  # Drop invalid amounts outside bounds

                    elif fn_name == "ask_clarification":
                        clarification = str(args.get("question", "")).strip()

        except MetaClientError:
            # On Meta API failure (timeout, 5xx, 429 exhaust), gracefully fall back
            specs, clar = rule_based_fallback_parser(clean_text, source_label="fallback")
            draft_specs = specs
            clarification = clar
            source_label = "fallback"

    # Step 2: Create DraftEntry objects in database
    created_drafts: List[DraftEntry] = []
    for spec in draft_specs:
        cust_name = spec["customer_name"]
        exact_customer, suggested_name = find_matching_customer(cust_name)

        note_val = spec.get("note", "")
        if suggested_name and not exact_customer:
            note_val = f"Suggested match: '{suggested_name}' | {note_val}".strip(" |")

        draft = DraftEntry.objects.create(
            source_text=clean_text,
            customer_name=exact_customer.name if exact_customer else cust_name,
            matched_customer=exact_customer,
            kind=spec["kind"],
            amount=Decimal(str(spec["amount"])),
            note=note_val,
            status=DraftStatus.PENDING,
            source_label=source_label,
            batch_id=batch_id,
        )
        created_drafts.append(draft)

    return ParseResult(
        batch_id=batch_id,
        drafts=created_drafts,
        clarification=clarification,
        source_label=source_label,
        latency_ms=latency_ms,
        usage_tokens=usage_tokens,
        raw_text=clean_text,
    )


def confirm(draft_id: Union[int, str], edits: Optional[Dict[str, Any]] = None) -> Tuple[LedgerEntry, Decimal]:
    """Confirm a pending draft entry and persist it to the official ledger.

    Args:
        draft_id: Primary key of the DraftEntry.
        edits: Optional overrides for customer_name, kind, amount, or note.

    Returns:
        (saved_ledger_entry, customer_new_balance)

    Raises:
        ParsingError: If draft is not found or has already been decided.
        LedgerValidationError: If edited fields fail business rules.
    """
    try:
        draft = DraftEntry.objects.get(id=draft_id)
    except (DraftEntry.DoesNotExist, ValueError) as exc:
        raise ParsingError(f"DraftEntry with ID {draft_id} not found.") from exc

    if draft.status == DraftStatus.CONFIRMED:
        # Idempotent safeguard: prevent double save
        raise ParsingError(f"Draft {draft_id} is already confirmed.")

    if draft.status == DraftStatus.REJECTED:
        raise ParsingError(f"Draft {draft_id} has been rejected and cannot be confirmed.")

    # Apply any owner edits
    final_name = draft.customer_name
    final_kind = draft.kind
    final_amount = draft.amount
    final_note = draft.note

    if edits:
        if "customer_name" in edits and edits["customer_name"]:
            final_name = str(edits["customer_name"]).strip()
        if "kind" in edits and edits["kind"]:
            final_kind = str(edits["kind"]).strip().lower()
        if "amount" in edits and edits["amount"] is not None:
            final_amount = validate_and_normalize_amount(edits["amount"])
        if "note" in edits:
            final_note = str(edits.get("note", "")).strip()

    # Create the official ledger entry
    entry = add_entry(
        customer_name=final_name,
        kind=final_kind,
        amount=final_amount,
        note=final_note,
        source_text=draft.source_text,
    )

    # Mark draft as confirmed
    draft.status = DraftStatus.CONFIRMED
    draft.decided_at = timezone.now()
    draft.customer_name = final_name
    draft.kind = final_kind
    draft.amount = final_amount
    draft.note = final_note
    draft.matched_customer = entry.customer
    draft.save()

    new_balance = get_balance(entry.customer)
    return entry, new_balance


def reject(draft_id: Union[int, str]) -> DraftEntry:
    """Reject a pending draft entry without creating any ledger entry."""
    try:
        draft = DraftEntry.objects.get(id=draft_id)
    except (DraftEntry.DoesNotExist, ValueError) as exc:
        raise ParsingError(f"DraftEntry with ID {draft_id} not found.") from exc

    if draft.status == DraftStatus.CONFIRMED:
        raise ParsingError(f"Cannot reject draft {draft_id} because it was already confirmed.")

    draft.status = DraftStatus.REJECTED
    draft.decided_at = timezone.now()
    draft.save(update_fields=["status", "decided_at"])
    return draft
