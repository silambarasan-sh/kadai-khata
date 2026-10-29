"""Demo mode protections: Per-IP rate limiting and global daily live API call budget."""

import datetime
from typing import Optional
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone

from .models import DailyLiveCallBudget, RateLimitRecord


def get_client_ip(request: HttpRequest) -> str:
    """Extract client IP address, trusting ONLY the first hop in X-Forwarded-For.

    Security & Reverse Proxy Architecture:
    In cloud deployments behind reverse proxies (Render, Cloudflare, AWS ALB),
    the leftmost IP in the X-Forwarded-For header is the original client IP
    appended by the edge proxy. Intermediate proxies append subsequent hops.
    By reading strictly the first hop (index 0), we prevent IP spoofing attacks
    where an untrusted client or intermediate proxy forges subsequent headers.
    If X-Forwarded-For is not present, falls back to REMOTE_ADDR.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # Trust only the first hop (leftmost IP)
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[0]
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def check_rate_limit(request: HttpRequest, action: str, limit: Optional[int] = None) -> Optional[JsonResponse]:
    """Check hourly rate limit for client IP on the given action.

    Returns HTTP 429 JsonResponse if limit is exceeded, or None if permitted.
    """
    if not getattr(settings, "DEMO_MODE", False):
        return None

    if limit is None:
        if action in ("parse", "text"):
            limit = getattr(settings, "DEMO_RATE_LIMIT_TEXT", 20)
        elif action == "ask":
            limit = getattr(settings, "DEMO_RATE_LIMIT_ASK", 20)
        elif action == "photo":
            limit = getattr(settings, "DEMO_RATE_LIMIT_PHOTO", 5)
        elif action == "agent":
            limit = getattr(settings, "DEMO_RATE_LIMIT_AGENT", 3)
        elif action == "reminder":
            limit = getattr(settings, "DEMO_RATE_LIMIT_REMINDER", 20)
        elif action in ("voice", "transcribe"):
            limit = getattr(settings, "DEMO_RATE_LIMIT_VOICE", 10)
        else:
            limit = 20

    ip = get_client_ip(request)
    now = timezone.now()
    window_start = now - datetime.timedelta(hours=1)

    recent_hits = RateLimitRecord.objects.filter(
        ip=ip,
        action=action,
        created_at__gte=window_start,
    ).count()

    if recent_hits >= limit:
        friendly_messages = {
            "parse": "You have reached the demo limit of 20 text transactions per hour. Please wait a little while before trying again.",
            "text": "You have reached the demo limit of 20 text transactions per hour. Please wait a little while before trying again.",
            "ask": "You have reached the demo limit of 20 questions per hour. Please wait a little while before trying again.",
            "photo": "You have reached the demo limit of 5 notebook photos per hour. Please wait a little while before trying again.",
            "agent": "You have reached the demo limit of 3 collections reviews per hour. Please wait a little while before trying again.",
            "reminder": "You have reached the demo limit of 20 reminders per hour. Please wait a little while before trying again.",
            "voice": "You have reached the demo limit of 10 voice transcriptions per hour. Please wait a little while before trying again.",
            "transcribe": "You have reached the demo limit of 10 voice transcriptions per hour. Please wait a little while before trying again.",
        }
        user_msg = friendly_messages.get(
            action,
            f"Hourly rate limit exceeded ({recent_hits}/{limit} per hour). Please try again later."
        )
        return JsonResponse(
            {
                "status": "error",
                "error": user_msg,
                "action": action,
                "limit_per_hour": limit,
            },
            status=429,
        )

    # Record the hit
    RateLimitRecord.objects.create(ip=ip, action=action, created_at=now)
    return None


def get_current_utc_date() -> datetime.date:
    """Return the current date in UTC."""
    return timezone.now().astimezone(datetime.timezone.utc).date()


def get_daily_live_calls(date: Optional[datetime.date] = None) -> int:
    """Return current day's live Meta API call count (stored in DB, resets at UTC midnight)."""
    try:
        target_date = date or get_current_utc_date()
        obj = DailyLiveCallBudget.objects.filter(date=target_date).first()
        return obj.call_count if obj else 0
    except Exception:
        return 0


def increment_daily_live_calls(count: int = 1, date: Optional[datetime.date] = None) -> int:
    """Increment current day's live Meta API call count in DB."""
    try:
        target_date = date or get_current_utc_date()
        with transaction.atomic():
            obj, _ = DailyLiveCallBudget.objects.select_for_update().get_or_create(
                date=target_date,
                defaults={"call_count": 0},
            )
            obj.call_count += count
            obj.save(update_fields=["call_count"])
            return obj.call_count
    except Exception:
        return 0


def is_daily_budget_exceeded() -> bool:
    """Check if the global daily live-call budget is exceeded.

    Resets automatically at UTC midnight because queries are partitioned by UTC date.
    """
    if not getattr(settings, "DEMO_MODE", False):
        return False
    budget = getattr(settings, "DEMO_DAILY_LIVE_CALLS", 300)
    return get_daily_live_calls() >= budget
