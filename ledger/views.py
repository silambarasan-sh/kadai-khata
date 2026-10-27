"""JSON API Views for Kadai Khata.

Provides endpoints for:
- POST /api/parse/     : Parse Tanglish speech/text into DraftEntry records
- POST /api/confirm/   : Confirm and save a draft entry to the official ledger
- POST /api/reject/    : Reject a draft entry without saving
- GET  /api/customers/ : Retrieve customers with calculated balances
"""

import json
from decimal import Decimal
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import DraftEntry
from .parsing import ParsingError, confirm, parse_text, reject
from .services import LedgerValidationError, list_customers_with_balance


def _json_error(message: str, status: int = 400) -> JsonResponse:
    """Return a clean JSON error response without internal stack traces."""
    return JsonResponse({"error": message, "status": "error"}, status=status)


def _serialize_draft(draft: DraftEntry) -> dict:
    return {
        "id": draft.id,
        "customer_name": draft.customer_name,
        "matched_customer_id": draft.matched_customer_id,
        "kind": draft.kind,
        "kind_display": draft.get_kind_display(),
        "amount": f"{draft.amount:.2f}",
        "note": draft.note,
        "status": draft.status,
        "warnings": draft.warnings or [],
        "candidates": draft.candidates or [],
        "source_label": draft.source_label,
        "source_text": draft.source_text,
        "batch_id": str(draft.batch_id),
        "created_at": draft.created_at.isoformat(),
    }


def index(request: HttpRequest) -> JsonResponse:
    """Health check / root info."""
    return JsonResponse({"status": "ok", "app": "Kadai Khata", "version": "1.0.0"})


@csrf_exempt
@require_POST
def api_parse(request: HttpRequest) -> JsonResponse:
    """Parse a Tanglish text input into proposed draft entries."""
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    text = data.get("text", "")
    if not str(text).strip():
        return _json_error("Field 'text' is required and cannot be empty.")

    try:
        result = parse_text(text)
    except ParsingError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Unexpected parsing failure: {str(exc)}", status=500)

    return JsonResponse({
        "status": "ok",
        "batch_id": str(result.batch_id),
        "drafts": [_serialize_draft(d) for d in result.drafts],
        "clarification": result.clarification,
        "source_label": result.source_label,
        "latency_ms": result.latency_ms,
        "usage": result.usage_tokens,
    })


@csrf_exempt
@require_POST
def api_confirm(request: HttpRequest) -> JsonResponse:
    """Confirm a draft entry (with optional edits) to create a ledger entry."""
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    draft_id = data.get("draft_id")
    if not draft_id:
        return _json_error("Field 'draft_id' is required.")

    edits = data.get("edits")

    try:
        entry, new_balance = confirm(draft_id=draft_id, edits=edits)
    except (ParsingError, LedgerValidationError) as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Failed to confirm entry: {str(exc)}", status=500)

    return JsonResponse({
        "status": "ok",
        "message": "Entry successfully confirmed and saved to ledger.",
        "entry": {
            "id": entry.id,
            "customer_id": entry.customer_id,
            "customer_name": entry.customer.name,
            "kind": entry.kind,
            "amount": str(entry.amount),
            "note": entry.note,
            "created_at": entry.created_at.isoformat(),
        },
        "new_balance": str(new_balance),
    })


@csrf_exempt
@require_POST
def api_reject(request: HttpRequest) -> JsonResponse:
    """Reject a draft entry so it is never committed to the ledger."""
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    draft_id = data.get("draft_id")
    if not draft_id:
        return _json_error("Field 'draft_id' is required.")

    try:
        draft = reject(draft_id=draft_id)
    except ParsingError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Failed to reject draft: {str(exc)}", status=500)

    return JsonResponse({
        "status": "ok",
        "message": "Draft entry rejected.",
        "draft_id": draft.id,
        "draft_status": draft.status,
    })


@require_GET
def api_customers(request: HttpRequest) -> JsonResponse:
    """List all customers with their calculated total credit, payments, and balances."""
    customers = list_customers_with_balance()
    data = []
    for c in customers:
        data.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "balance": str(c.balance),
            "total_credit": str(c.total_credit),
            "total_paid": str(c.total_paid),
            "entry_count": c.entry_count,
            "last_entry_at": c.last_entry_at.isoformat() if c.last_entry_at else None,
        })
    return JsonResponse({"status": "ok", "customers": data})
