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
from .prompts import LEDGER_TOOLS, build_chat_messages, build_system_prompt
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


HONORIFICS = {
    "akka", "anna", "annan", "thambi", "thangai", "thangachi",
    "paatti", "thatha", "mama", "maami", "amma", "appa",
    "aunty", "uncle", "bhai", "sir", "madam",
}


def normalize_customer_name(raw_name: str) -> Tuple[Optional[str], bool]:
    """Normalize customer names by stripping trailing and leading honorifics.

    Rules:
    - Strips: akka, anna, annan, thambi, thangai, thangachi, paatti, thatha,
      mama, maami, amma, appa, aunty, uncle, bhai, sir, madam.
    - 'Lakshmi akka' -> ('Lakshmi', False)
    - 'Uncle Suresh' -> ('Suresh', False)
    - 'Lakshmi-akka' -> ('Lakshmi', False)
    - If only an honorific remains (e.g. 'Annan' or 'Bhai') -> (None, True)
    """
    clean = (raw_name or "").strip()
    if not clean:
        return None, False

    # Also handle hyphens connecting honorifics e.g. 'Lakshmi-akka'
    clean = re.sub(r"-+", " ", clean).strip()
    tokens = clean.split()
    if not tokens:
        return None, False

    # Check if every token is an honorific
    if all(t.lower() in HONORIFICS for t in tokens):
        return None, True

    # Strip leading honorifics
    while tokens and tokens[0].lower() in HONORIFICS:
        tokens.pop(0)

    # Strip trailing honorifics
    while tokens and tokens[-1].lower() in HONORIFICS:
        tokens.pop()

    if not tokens:
        return None, True

    return " ".join(tokens), False


def find_matching_customers(raw_name: str) -> Tuple[Optional[Customer], List[str]]:
    """Match raw_name against existing customers with strict exact matching.

    Rules:
    - ONLY an exact case-insensitive full-name match is auto-matched (exact, []).
    - Any other match (first-name, partial like 'Kumar' vs 'Ravi Kumar', fuzzy)
      is a SUGGESTION with exact=None and candidates populated.

    Returns:
        (exact_match_customer, suggestions_list)
    """
    clean = (raw_name or "").strip()
    if not clean:
        return None, []

    # 1. Exact case-insensitive full-name match ONLY
    exact = Customer.objects.filter(name__iexact=clean).first()
    if exact:
        return exact, []

    # 2. Non-exact matches are suggestions:
    all_customers = list(Customer.objects.all())
    clean_lower = clean.lower()
    clean_words = set(re.findall(r"\w+", clean_lower))

    suggestions: List[str] = []
    seen: set = set()

    # (a) First-name / last-name / partial word overlap / substring
    for cust in all_customers:
        c_name_lower = cust.name.lower()
        c_words = set(re.findall(r"\w+", c_name_lower))
        if (clean_words & c_words) or (clean_lower in c_name_lower) or (c_name_lower in clean_lower):
            if cust.name not in seen:
                suggestions.append(cust.name)
                seen.add(cust.name)

    # (b) Fuzzy matches for typo tolerance
    all_names = [c.name for c in all_customers]
    fuzzy_matches = difflib.get_close_matches(clean, all_names, n=5, cutoff=0.65)
    for name in fuzzy_matches:
        if name not in seen:
            suggestions.append(name)
            seen.add(name)

    return None, suggestions


def find_matching_customer(raw_name: str) -> Tuple[Optional[Customer], Optional[str]]:
    """Backward compatible wrapper returning (exact, single_suggested)."""
    exact, candidates = find_matching_customers(raw_name)
    suggested = candidates[0] if len(candidates) == 1 else None
    return exact, suggested


def generate_draft_warnings(
    customer_name: str,
    matched_customer: Optional[Customer],
    kind: str,
    amount: Decimal,
    candidates: List[str],
) -> List[str]:
    """Generate intelligent safety warnings for shopkeeper review."""
    warnings: List[str] = []

    # Non-exact suggestion warning
    if not matched_customer and candidates:
        if len(candidates) == 1:
            warnings.append(
                f"Suggested match: '{candidates[0]}'. This is not an exact match; please verify before confirming."
            )
        else:
            warnings.append(
                f"Multiple candidate customers match '{customer_name}': {', '.join(candidates)}. "
                "Please select the correct customer before confirming."
            )

    # Warning 2: New customer with a payment_received
    if kind == EntryKind.PAYMENT_RECEIVED:
        if matched_customer is None:
            warnings.append(
                f"New customer '{customer_name}' recorded with a payment received. "
                "Verify if this is an advance payment or if customer name is misspelled."
            )
        else:
            # Warning 3: Payment larger than current balance (balance would go negative)
            current_balance = get_balance(matched_customer)
            if amount > current_balance:
                new_bal = current_balance - amount
                warnings.append(
                    f"Payment of Rs.{amount:.2f} exceeds current balance of Rs.{current_balance:.2f}. "
                    f"Customer balance will become negative (Rs.{new_bal:.2f})."
                )

    # Warning 4: Amount unusually large vs customer's history
    if matched_customer:
        entries = matched_customer.entries.all()
        if entries.exists():
            entry_amounts = [e.amount for e in entries]
            max_prev = max(entry_amounts)
            avg_prev = sum(entry_amounts, Decimal("0.00")) / len(entry_amounts)
            if amount > (avg_prev * 3) and amount > (max_prev * 2):
                warnings.append(
                    f"Amount Rs.{amount:.2f} is unusually large compared to {matched_customer.name}'s history "
                    f"(previous max: Rs.{max_prev:.2f}, average: Rs.{avg_prev:.2f})."
                )

    return warnings


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

        # Ignore item quantities with unit suffixes like '2 kilo', '10 kg', '5 liter', '2 packet'
        unit_pattern = r"\b\d+(?:\.\d+)?\s*(?:kilo|kg|liter|litre|packet|box|can|piece|ரூபாய்|rooba|rupees)?\b"
        c_clean_for_amt = re.sub(r"\b\d+\s*(?:kilo|kg|liter|litre|packet|box|can|piece)\b", "", c_lower)

        if found_amount is None:
            num_match = re.search(r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d{1,2})?)\s*(?:rupees|rooba|rs|/-)?", c_clean_for_amt)
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
                "annachi", "monthly", "balance", "arisi", "pooja", "samaiyal", "chai", "tea",
                "sugar", "oil", "soap", "box", "colgate", "paste", "surf", "excel", "water",
                "can", "packet", "bill", "podu", "print", "out", "whatsapp", "milk", "powder",
                "kilo", "kg", "liter", "litre", "code", "scan", "advance", "sales", "seal",
                "neram", "coin", "stock", "inventory", "price", "kaila", "oru", "chinna",
                "periya", "tharen", "enna", "kelu", "kudunga", "innum", "varala", "note",
                "pannikonga", "poriya", "anuppu", "rendu", "mathiri", "oruthar", "poirukaru",
                "iniku", "check", "pannu", "loose", "change", "kakan", "koraiva", "irukku",
                "thambi", "annan", "anna", "vechu", "eduthu", "vekkuran", "naalaikku", "pudhusa",
                "vantha", "aavin", "nethu", "netru", "sonna", "atha", "athai", "entry", "aagiduchu",
                "evlo", "vandhuruku", "vandhurukku", "maasa", "kadaisula", "panrom", "nu", "sonnaru",
                "antha", "நேத்து", "பாரு", "நேத்து", "நேத்து", "நேத்து", "aanju", "ayiram", "nooru", "ambadhu"
            }
            cleaned_words = []
            for token in c_text.split():
                clean_tok = re.sub(r"[^A-Za-z0-9-]", "", token)
                low_tok = clean_tok.lower()
                if low_tok.endswith("-ku"):
                    clean_tok = clean_tok[:-3]
                elif low_tok.endswith("ku") and len(clean_tok) > 3:
                    clean_tok = clean_tok[:-2]
                elif low_tok.endswith("-la"):
                    clean_tok = clean_tok[:-3]

                clean_alphanumeric = re.sub(r"[^A-Za-z0-9]", "", clean_tok)
                low_alpha = clean_alphanumeric.lower()

                if not clean_alphanumeric or low_alpha in skip_words or low_alpha in {"vara", "varala"} or clean_alphanumeric.isdigit():
                    continue

                # Never treat Tamil number words or udhaar/kadan labels as customer names
                if any(w in low_alpha for w in ["udhaar", "kadan", "ayiram", "nooru", "ambadhu", "ainooru"]):
                    continue

                cleaned_words.append(clean_alphanumeric)

            if cleaned_words and len(cleaned_words) <= 3:
                found_name = " ".join(cleaned_words)

        # Validate findings: MUST have customer name, amount, AND direction
        if found_name and found_amount and (is_credit or is_payment):
            norm_name, is_only_hon = normalize_customer_name(found_name)
            if is_only_hon:
                return extracted_entries, f"Customer name-il honorific ('{found_name}') mattum ulladhu. Customer peyar sollunga."
            if not norm_name:
                return extracted_entries, f"Yaaruku {found_amount} udhaar/panam? Customer name sollunga."
            found_name = norm_name

            kind = "credit_given" if is_credit else "payment_received"
            extracted_entries.append({
                "customer_name": found_name,
                "kind": kind,
                "amount": found_amount,
                "note": c_text,
            })
        elif not found_name and found_amount and (is_credit or is_payment):
            return extracted_entries, f"Yaaruku {found_amount} udhaar/panam? Customer name sollunga."
        elif found_name and not found_amount and (is_credit or is_payment):
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

    from ledger.demo_guards import is_daily_budget_exceeded

    if meta_mode == "mock":
        # Deterministic mock parsing
        specs, clar = rule_based_fallback_parser(clean_text, source_label="mock")
        draft_specs = specs
        clarification = clar
        source_label = "mock"
        latency_ms = 2.5
        usage_tokens = {"prompt_tokens": len(clean_text.split()), "completion_tokens": 15, "total_tokens": len(clean_text.split()) + 15}

    elif is_daily_budget_exceeded():
        # Demo budget reached: do NOT call Meta, use offline fallback parser
        specs, clar = rule_based_fallback_parser(clean_text, source_label="fallback")
        draft_specs = specs
        clarification = "Demo budget reached - offline mode"
        source_label = "fallback"
        latency_ms = 1.0
        usage_tokens = {"prompt_tokens": len(clean_text.split()), "completion_tokens": 15, "total_tokens": len(clean_text.split()) + 15}

    else:
        # Live Meta AI call
        client = MetaClient(mode="live")
        messages = build_chat_messages(existing_customer_names=existing_customers, user_text=clean_text)

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
                                norm_name, is_only_hon = normalize_customer_name(cust_name)
                                if is_only_hon:
                                    if not clarification:
                                        clarification = f"Customer name-il honorific ('{cust_name}') mattum ulladhu. Customer peyar sollunga."
                                elif norm_name:
                                    draft_specs.append({
                                        "customer_name": norm_name,
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
        exact_customer, candidates = find_matching_customers(cust_name)

        note_val = spec.get("note", "")
        if len(candidates) == 1 and not exact_customer:
            note_val = f"Suggested match: '{candidates[0]}' | {note_val}".strip(" |")

        dec_amt = Decimal(str(spec["amount"]))
        warnings_list = generate_draft_warnings(
            customer_name=exact_customer.name if exact_customer else cust_name,
            matched_customer=exact_customer,
            kind=spec["kind"],
            amount=dec_amt,
            candidates=candidates,
        )

        draft = DraftEntry.objects.create(
            source_text=clean_text,
            customer_name=exact_customer.name if exact_customer else cust_name,
            matched_customer=exact_customer,
            kind=spec["kind"],
            amount=dec_amt,
            note=note_val,
            status=DraftStatus.PENDING,
            source_label=source_label,
            batch_id=batch_id,
            warnings=warnings_list,
            candidates=candidates,
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

    # Guard: if multiple candidates were found, owner must explicitly choose customer_name
    if draft.candidates and len(draft.candidates) > 1:
        chosen = edits.get("customer_name") if edits else None
        if not chosen:
            raise ParsingError(
                f"Multiple candidate customers found: {', '.join(draft.candidates)}. "
                "You must specify the customer_name in edits before confirming."
            )

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
