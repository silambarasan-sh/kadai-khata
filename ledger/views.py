"""JSON API Views and UI template view for Kadai Khata.

Provides endpoints for:
- GET  /                                     : Serve Mobile-first UI
- POST /api/parse/                           : Parse Tanglish speech/text into DraftEntry records
- POST /api/confirm/                         : Confirm and save a draft entry to the official ledger
- POST /api/reject/                          : Reject a draft entry without saving
- GET  /api/customers/                       : Retrieve customers with calculated balances & aging
- GET  /api/customers/<id>/timeline/         : Retrieve chronological audit trail for a customer
- POST /api/reverse/                         : Reverse an entry (creates offsetting entry, no deletes)
- POST /api/reminder/                        : Generate verified polite payment reminder
"""

import json
from decimal import Decimal
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Customer, DraftEntry
from .parsing import ParsingError, confirm, parse_text, reject
from .reminders import generate_reminder
from .services import (
    LedgerValidationError,
    get_customer_timeline,
    list_customers_with_balance,
    reverse_entry,
)
from .voice_client import (
    validate_wav_bytes,
    transcribe_audio_bytes,
    VoiceBadRequestError,
    VoiceAuthenticationError,
    VoiceRateLimitError,
    VoiceServerError,
    VoiceClientError,
)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    """Return a clean JSON error response without internal stack traces or leaked secrets."""
    from django.conf import settings
    clean_msg = str(message)
    for secret in (
        getattr(settings, "MODEL_API_KEY", ""),
        getattr(settings, "PARTNER_API_KEY", ""),
        getattr(settings, "SECRET_KEY", ""),
    ):
        if secret and len(secret) > 4:
            clean_msg = clean_msg.replace(secret, "[REDACTED]")
    return JsonResponse({"error": clean_msg, "status": "error"}, status=status)


def _serialize_draft(draft: DraftEntry) -> dict:
    return {
        "id": draft.id,
        "customer_name": draft.customer_name,
        "name_latin": getattr(draft, "name_latin", ""),
        "matched_customer_id": draft.matched_customer_id,
        "is_exact_match": bool(draft.matched_customer_id),
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


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    """Return JSON response on CSRF validation failures instead of generic HTML."""
    return JsonResponse(
        {"status": "error", "error": f"CSRF verification failed: {reason or 'Invalid or missing CSRF token'}"},
        status=403,
    )


@ensure_csrf_cookie
def index(request: HttpRequest):
    """Serve the single-page application UI."""
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"status": "ok", "app": "Kadai Khata", "version": "1.0.0"})
    return render(request, "index.html")


@require_POST
def api_parse(request: HttpRequest) -> JsonResponse:
    """Parse a Tanglish text input into proposed draft entries."""
    from .demo_guards import check_rate_limit
    rate_err = check_rate_limit(request, "parse")
    if rate_err:
        return rate_err

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    text = data.get("text", "")
    if not str(text).strip():
        return _json_error("Field 'text' is required and cannot be empty.")

    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower()
        if provider not in ("meta", "partner"):
            return _json_error("Invalid provider. Must be 'meta' or 'partner'.", status=400)

    try:
        result = parse_text(text, provider=provider)
    except ParsingError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Unexpected parsing failure: {str(exc)}", status=500)

    serialized_drafts = [_serialize_draft(d) for d in result.drafts]
    for d_dict in serialized_drafts:
        d_dict["badge_label"] = result.badge_label
        d_dict["provider"] = result.provider
        d_dict["model"] = result.model

    return JsonResponse({
        "status": "ok",
        "batch_id": str(result.batch_id),
        "drafts": serialized_drafts,
        "clarification": result.clarification,
        "source_label": result.source_label,
        "provider": result.provider,
        "model": result.model,
        "badge_label": result.badge_label,
        "latency_ms": result.latency_ms,
        "usage": result.usage_tokens,
    })


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
            "amount": f"{entry.amount:.2f}",
            "note": entry.note,
            "created_at": entry.created_at.isoformat(),
        },
        "new_balance": f"{new_balance:.2f}",
    })


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
    """List all customers with balances, aging indicators, and total outstanding."""
    customers = list_customers_with_balance()
    now = timezone.now()
    data = []
    total_outstanding = Decimal("0.00")

    for c in customers:
        balance_dec = Decimal(str(c.balance))
        if balance_dec > Decimal("0.00"):
            total_outstanding += balance_dec

        days = 0
        if c.last_entry_at:
            days = max(0, (now - c.last_entry_at).days)

        if days <= 30:
            aging_bucket = "0-30"
        elif days <= 60:
            aging_bucket = "31-60"
        else:
            aging_bucket = "60+"

        data.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "balance": f"{balance_dec:.2f}",
            "total_credit": f"{c.total_credit:.2f}",
            "total_paid": f"{c.total_paid:.2f}",
            "entry_count": c.entry_count,
            "last_entry_at": c.last_entry_at.isoformat() if c.last_entry_at else None,
            "days_since_last_entry": days,
            "aging_bucket": aging_bucket,
        })

    return JsonResponse({
        "status": "ok",
        "total_outstanding": f"{total_outstanding:.2f}",
        "customers": data,
    })


@require_GET
def api_customer_timeline(request: HttpRequest, customer_id: int) -> JsonResponse:
    """Fetch chronological entries and running balance for a customer."""
    try:
        timeline = get_customer_timeline(customer_id)
    except LedgerValidationError as exc:
        return _json_error(str(exc), status=404)
    except Exception as exc:
        return _json_error(f"Failed to fetch timeline: {str(exc)}", status=500)

    return JsonResponse({"status": "ok", **timeline})


@require_POST
def api_reverse(request: HttpRequest) -> JsonResponse:
    """Reverse a ledger entry (creates an offsetting audit entry, no deletion)."""
    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    entry_id = data.get("entry_id")
    if not entry_id:
        return _json_error("Field 'entry_id' is required.")

    reason = data.get("reason", "")
    try:
        reversal_entry, new_balance = reverse_entry(entry_id=entry_id, reason=reason)
    except LedgerValidationError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Failed to reverse entry: {str(exc)}", status=500)

    return JsonResponse({
        "status": "ok",
        "message": f"Entry #{entry_id} successfully reversed by #{reversal_entry.id}.",
        "reversal_entry": {
            "id": reversal_entry.id,
            "customer_id": reversal_entry.customer_id,
            "customer_name": reversal_entry.customer.name,
            "kind": reversal_entry.kind,
            "amount": f"{reversal_entry.amount:.2f}",
            "note": reversal_entry.note,
            "created_at": reversal_entry.created_at.isoformat(),
            "reversed_entry_id": reversal_entry.reversed_entry_id,
        },
        "reversed_entry_id": entry_id,
        "new_balance": f"{new_balance:.2f}",
    })


@require_POST
def api_reminder(request: HttpRequest) -> JsonResponse:
    """Generate a polite, verified payment reminder message for a customer."""
    from .demo_guards import check_rate_limit
    rate_err = check_rate_limit(request, "reminder")
    if rate_err:
        return rate_err

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    customer_id = data.get("customer_id")
    if not customer_id:
        return _json_error("Field 'customer_id' is required.")

    language = str(data.get("language", "ta")).strip().lower()
    tone = str(data.get("tone", "soft")).strip().lower()

    if language not in {"ta", "en", "tanglish"}:
        language = "ta"
    if tone not in {"soft", "firm"}:
        tone = "soft"

    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower()
        if provider not in ("meta", "partner"):
            return _json_error("Invalid provider. Must be 'meta' or 'partner'.", status=400)

    try:
        result = generate_reminder(customer_id=int(customer_id), language=language, tone=tone, provider=provider)
    except (Customer.DoesNotExist, ValueError):
        return _json_error(f"Customer #{customer_id} not found.", status=404)
    except Exception as exc:
        return _json_error(f"Failed to generate reminder: {str(exc)}", status=500)

    return JsonResponse({
        "status": "ok",
        "customer_id": result.customer_id,
        "customer_name": result.customer_name,
        "phone": result.phone,
        "balance": result.balance,
        "days_overdue": result.days_overdue,
        "language": result.language,
        "tone": result.tone,
        "message": result.message,
        "verified": result.verified,
        "source_label": result.source_label,
        "provider": result.provider,
        "model": result.model,
        "badge_label": result.badge_label,
        "whatsapp_url": result.whatsapp_url,
    })


@require_POST
def api_agent_run(request: HttpRequest) -> JsonResponse:
    """Trigger a new Daily Collections Agent review run."""
    from .demo_guards import check_rate_limit, is_daily_budget_exceeded
    rate_err = check_rate_limit(request, "agent")
    if rate_err:
        return rate_err

    if is_daily_budget_exceeded():
        return _json_error(
            "Demo budget reached - offline mode. Daily collections agent run is temporarily paused.",
            status=200,
        )

    from .agent import AgentRunner

    mode = None
    if request.body:
        try:
            data = json.loads(request.body.decode("utf-8"))
            mode = data.get("mode")
        except Exception:
            pass

    runner = AgentRunner(mode=mode)
    run_obj = runner.run()

    from .agent_replay import verify_run_replay
    replay_info = verify_run_replay(run_obj.id)

    return JsonResponse({
        "status": "ok",
        "run": {
            "id": run_obj.id,
            "source_label": run_obj.source_label,
            "status": run_obj.status,
            "total_tokens": run_obj.total_tokens,
            "latency_ms": run_obj.latency_ms,
            "final_hash": run_obj.final_hash,
            "chain_valid": replay_info.get("chain_valid", True),
            "created_at": run_obj.created_at.isoformat(),
            "plan": run_obj.plan_json,
            "steps_count": run_obj.steps.count(),
        },
    })


@require_GET
def api_agent_run_detail(request: HttpRequest, run_id: int) -> JsonResponse:
    """Fetch details and full audit trace for an AgentRun."""
    from .models import AgentRun
    from .agent_replay import verify_run_replay

    try:
        run_obj = AgentRun.objects.get(id=run_id)
    except AgentRun.DoesNotExist:
        return _json_error(f"AgentRun #{run_id} not found.", status=404)

    replay_info = verify_run_replay(run_obj.id)
    steps_data = []
    for s in run_obj.steps.all().order_by("index"):
        steps_data.append({
            "index": s.index,
            "kind": s.kind,
            "name": s.name,
            "args": s.args_json,
            "result": s.result_json,
            "summary": s.result_summary,
            "latency_ms": s.latency_ms,
            "tokens": s.tokens,
            "prev_hash": s.prev_hash,
            "step_hash": s.step_hash,
        })

    return JsonResponse({
        "status": "ok",
        "run": {
            "id": run_obj.id,
            "source_label": run_obj.source_label,
            "status": run_obj.status,
            "total_tokens": run_obj.total_tokens,
            "latency_ms": run_obj.latency_ms,
            "final_hash": run_obj.final_hash,
            "chain_valid": replay_info.get("chain_valid", False),
            "created_at": run_obj.created_at.isoformat(),
            "plan": run_obj.plan_json,
            "steps": steps_data,
        },
    })


@require_POST
def api_agent_approve(request: HttpRequest) -> JsonResponse:
    """Approve a collection proposal for a customer and draft a reminder.

    Does not send anything and creates NO ledger entry.
    """
    from .models import AgentRun

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    run_id = data.get("run_id")
    customer_id = data.get("customer_id")
    if not run_id or not customer_id:
        return _json_error("Fields 'run_id' and 'customer_id' are required.")

    try:
        run_obj = AgentRun.objects.get(id=run_id)
    except AgentRun.DoesNotExist:
        return _json_error(f"AgentRun #{run_id} not found.", status=404)

    try:
        customer = Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        return _json_error(f"Customer #{customer_id} not found.", status=404)

    # Find the corresponding action if available to get suggested tone
    tone = "soft"
    if run_obj.plan_json and "actions" in run_obj.plan_json:
        for a in run_obj.plan_json["actions"]:
            if a.get("customer_id") == int(customer_id):
                tone = a.get("tone", "soft")
                break

    language = data.get("language", "ta")
    result = generate_reminder(customer_id=customer.id, language=language, tone=tone)

    return JsonResponse({
        "status": "ok",
        "run_id": run_obj.id,
        "customer_id": result.customer_id,
        "customer_name": result.customer_name,
        "phone": result.phone,
        "balance": result.balance,
        "days_overdue": result.days_overdue,
        "language": result.language,
        "tone": result.tone,
        "message": result.message,
        "verified": result.verified,
        "source_label": result.source_label,
        "whatsapp_url": result.whatsapp_url,
    })


@require_POST
def api_ask(request: HttpRequest) -> JsonResponse:
    """Read-only question answering endpoint about customer balances."""
    from .demo_guards import check_rate_limit
    rate_err = check_rate_limit(request, "ask")
    if rate_err:
        return rate_err

    from .ask import answer_question

    try:
        data = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return _json_error("Invalid JSON payload.")

    question = str(data.get("question", "")).strip()
    if not question:
        return _json_error("Field 'question' is required.")

    provider = data.get("provider")
    if provider is not None:
        provider = str(provider).strip().lower()
        if provider not in ("meta", "partner"):
            return _json_error("Invalid provider. Must be 'meta' or 'partner'.", status=400)

    mode = data.get("mode")
    result = answer_question(question, mode=mode, provider=provider)
    return JsonResponse({"status": "ok", **result})


@require_POST
def api_parse_photo(request: HttpRequest) -> JsonResponse:
    """Parse a notebook photo uploaded via multipart form data into pending DraftEntry records.
    Image is processed in-memory only and never written to disk or the database.
    """
    from .demo_guards import check_rate_limit, is_daily_budget_exceeded
    rate_err = check_rate_limit(request, "photo")
    if rate_err:
        return rate_err

    if is_daily_budget_exceeded():
        return _json_error(
            "Demo budget reached - offline mode. Notebook photo scanning is temporarily paused to conserve demo credits.",
            status=200,
        )

    from .photo_parser import parse_photo_in_memory, ALLOWED_MIME_TYPES, MAX_PHOTO_SIZE_BYTES

    if "image" not in request.FILES:
        return _json_error("Multipart field 'image' is required.", status=400)

    uploaded_file = request.FILES["image"]

    # Validate size
    if uploaded_file.size > MAX_PHOTO_SIZE_BYTES:
        return _json_error(
            f"Image size exceeds 4MB limit ({uploaded_file.size / 1024 / 1024:.2f}MB).",
            status=400,
        )

    # Validate content type
    content_type = uploaded_file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        name_lower = uploaded_file.name.lower()
        if name_lower.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif name_lower.endswith(".png"):
            content_type = "image/png"
        elif name_lower.endswith(".webp"):
            content_type = "image/webp"
        else:
            return _json_error(
                f"Unsupported file format '{content_type}'. Please upload JPEG, PNG, or WebP.",
                status=400,
            )

    # Read bytes into memory strictly
    image_bytes = uploaded_file.read()

    mode = request.POST.get("mode") or request.GET.get("mode")

    try:
        result = parse_photo_in_memory(image_bytes=image_bytes, mime_type=content_type, mode=mode)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Failed to process image: {str(exc)}", status=500)

    if result.error:
        return JsonResponse({
            "status": "error",
            "error": result.error,
            "batch_id": str(result.batch_id),
            "drafts": [],
            "cancelled_rows": [],
            "unreadable_rows": [],
            "page_totals": result.page_totals,
            "calculated_totals": result.calculated_totals,
            "total_check": result.total_check,
            "source_label": result.source_label,
            "latency_ms": result.latency_ms,
            "usage": result.usage_tokens,
        }, status=200)

    return JsonResponse({
        "status": "ok",
        "batch_id": str(result.batch_id),
        "drafts": [_serialize_draft(d) for d in result.drafts],
        "cancelled_rows": result.cancelled_rows,
        "unreadable_rows": result.unreadable_rows,
        "page_totals": result.page_totals,
        "calculated_totals": result.calculated_totals,
        "total_check": result.total_check,
        "source_label": result.source_label,
        "latency_ms": result.latency_ms,
        "usage": result.usage_tokens,
    })


@require_POST
def api_transcribe(request: HttpRequest) -> JsonResponse:
    """Endpoint for audio transcription via Meta Muse Voice Transcribe.

    Held in memory only: audio bytes are never written to disk or database.
    """
    from .demo_guards import check_rate_limit, is_daily_budget_exceeded, increment_daily_live_calls
    rate_err = check_rate_limit(request, "voice")
    if rate_err:
        return rate_err

    if is_daily_budget_exceeded():
        return _json_error(
            "Demo budget reached - voice transcription is temporarily paused to conserve demo credits.",
            status=200,
        )

    if "audio" not in request.FILES:
        return _json_error("Multipart field 'audio' is required.", status=400)

    uploaded_file = request.FILES["audio"]
    audio_bytes = uploaded_file.read()

    try:
        duration, nchannels, sampwidth, framerate = validate_wav_bytes(audio_bytes)
    except VoiceBadRequestError as exc:
        return _json_error(str(exc), status=400)
    except Exception as exc:
        return _json_error(f"Invalid audio format: {exc}", status=400)

    # Keywords = names of existing customers only (max 50, no phone numbers, no balances)
    from .models import Customer
    customer_names = list(Customer.objects.values_list("name", flat=True)[:50])

    # languageBias from settings
    bias_str = getattr(settings, "VOICE_LANGUAGE_BIAS", "Tamil")
    language_bias = [b.strip() for b in bias_str.split(",") if b.strip()] if bias_str else None

    # Meta mode: check if mock or live
    req_mode = request.POST.get("mode") or request.GET.get("mode")
    meta_mode = (req_mode or getattr(settings, "META_MODE", "mock")).strip().lower()
    is_mock = meta_mode == "mock"

    try:
        res = transcribe_audio_bytes(
            audio_bytes=audio_bytes,
            filename=uploaded_file.name or "audio.wav",
            language_bias=language_bias,
            keywords=customer_names,
            mock_mode=is_mock,
        )
    except VoiceBadRequestError as exc:
        return _json_error(str(exc), status=400)
    except VoiceAuthenticationError:
        return _json_error("Voice transcription service authentication failed. Please check configuration.", status=503)
    except VoiceRateLimitError:
        return _json_error("Upstream speech-to-text rate limit exceeded. Please try again shortly.", status=429)
    except (VoiceServerError, VoiceClientError):
        return _json_error("Voice transcription service is temporarily unavailable. Please try again later.", status=502)
    except Exception:
        return _json_error("An unexpected error occurred during audio transcription.", status=500)

    source_label = "mock" if is_mock else "live"
    if not is_mock:
        increment_daily_live_calls(1)

    return JsonResponse({
        "status": "ok",
        "transcript": res.transcript,
        "source_label": source_label,
        "latency_ms": res.latency_ms,
        "audio_seconds": res.audio_seconds,
        "estimated_cost_usd": res.estimated_cost,
    })




