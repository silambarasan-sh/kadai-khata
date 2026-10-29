# Kadai Khata &mdash; Public Demo Deployment Guide

This guide details instructions for deploying Kadai Khata as a public, judge-facing demo application on [Render](https://render.com) (or any containerized Linux environment).

---

## 1. Quick Deploy with Render Blueprint (`render.yaml`)

The repository includes a root `render.yaml` specification that configures:
- Build step: `./render_build.sh` (`pip install -r requirements.txt` and `python manage.py collectstatic --no-input`)
- Start step: `./render_start.sh` (database migrations, idempotent demo seeding if empty, and Gunicorn startup)
- Environment variable defaults with secure production values

### Step-by-Step Deployment:
1. Push your repository branch to GitHub.
2. In the [Render Dashboard](https://dashboard.render.com), click **New +** &rarr; **Blueprint**.
3. Select your repository. Render automatically reads `render.yaml`.
4. In the environment setup, configure `MODEL_API_KEY` (which is marked `sync: false` for security).
5. Click **Apply**. Render will build and deploy the application.

---

## 2. Server Startup & Architecture

The application starts via `render_start.sh`:
```bash
python manage.py migrate --no-input
python manage.py seed_demo_data --if-empty
exec gunicorn kadai_khata.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --timeout 120
```

> [!IMPORTANT]
> **Gunicorn Configuration**:
> Gunicorn runs with `--timeout 120` and `--worker-class gthread` (`--workers 2 --threads 4`). The extended timeout is required because complex handwritten notebook photo requests (`/api/parse-photo/`) can take up to 25–30 seconds for multimodal LLM vision inference; the default 30-second worker timeout would prematurely terminate these requests.

> [!NOTE]
> **Ephemeral Storage Notice**:
> Render free-tier instances use ephemeral disks. The SQLite database may reset when the service restarts or spins down after inactivity. On startup, `python manage.py seed_demo_data --if-empty` automatically re-populates the 8 fictional Tamil Nadu demo customers and 40 transactions whenever the database is empty.

---

## 3. Verifying the Deployment (Health Check)

Once deployed, probe the health endpoint:
```bash
curl -i https://<your-service-url>.onrender.com/healthz
```

Expected Response (`HTTP 200 OK`):
```json
{
  "status": "ok",
  "mode": "live"
}
```

---

## 4. Complete Environment Variables Reference

All environment variables use placeholder values below. Never commit real keys.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_DEBUG` | Optional | `False` | Must be `False` for production deployments. |
| `DJANGO_SECRET_KEY` | Required if not debug | `[GENERATE_SECRET_KEY]` | Cryptographic secret key for session and CSRF signing. Fails fast if missing when `DJANGO_DEBUG=False`. |
| `ALLOWED_HOSTS` | Required | `.onrender.com,localhost,127.0.0.1` | Comma-separated list of valid host headers. |
| `CSRF_TRUSTED_ORIGINS` | Required | `https://*.onrender.com` | Comma-separated list of trusted origins for CSRF protection. |
| `DJANGO_ENABLE_ADMIN` | Optional | `0` | Set to `1` to enable the `/admin/` route. Default `0` disables it in public demos. |
| `DATABASE_PATH` | Optional | `""` | Optional explicit path for the SQLite database (defaults to `BASE_DIR / db.sqlite3`). |
| `DEMO_MODE` | Optional | `1` | Enables public demo banner, hourly rate limits, and daily live budget tracking. |
| `DEMO_DAILY_LIVE_CALLS` | Optional | `300` | Global daily live Meta API request budget (resets at UTC midnight). |
| `DEMO_RATE_LIMIT_TEXT` | Optional | `20` | Maximum text parse / ask transactions per client IP per hour. |
| `DEMO_RATE_LIMIT_PHOTO` | Optional | `5` | Maximum notebook photo uploads per client IP per hour. |
| `DEMO_RATE_LIMIT_VOICE` | Optional | `10` | Maximum speech-to-text transcriptions per client IP per hour. |
| `DEMO_RATE_LIMIT_AGENT` | Optional | `3` | Maximum daily collections agent reviews per client IP per hour. |
| `DEMO_RATE_LIMIT_REMINDER` | Optional | `20` | Maximum reminder drafts per client IP per hour. |
| `VOICE_LANGUAGE_BIAS` | Optional | `"Tamil"` | Target language bias for Meta Muse Voice Transcribe. Comma-separated. |
| `VOICE_MAX_SECONDS` | Optional | `20` | Maximum recording duration in seconds accepted for voice upload. |
| `VOICE_MAX_BYTES` | Optional | `2000000` | Maximum raw audio payload size in bytes (2 MB). |
| `META_VOICE_TIMEOUT_SECONDS` | Optional | `60.0` | Timeout in seconds for Meta Muse Voice Transcribe API calls. |
| `MODEL_API_KEY` | Required for live | `"LLM\|numeric_id\|secret_token"` | Meta Model API authentication key via OpenAI SDK. Enclose in quotes. |
| `META_BASE_URL` | Optional | `https://api.meta.ai/v1` | Base URL for the OpenAI-compatible Meta completions endpoint. |
| `META_MODEL` | Optional | `muse-spark-1.3` | Model identifier for text, tool calling, and multimodal vision. |
| `META_MODE` | Optional | `live` | Set to `live` for real API calls, or `mock` for deterministic offline testing. |
| `META_TIMEOUT_SECONDS` | Optional | `30.0` | Timeout in seconds for standard text/chat completions. |
| `META_VISION_TIMEOUT_SECONDS` | Optional | `90.0` | Timeout in seconds for multimodal notebook photo parsing. |
| `META_VISION_REASONING_EFFORT` | Optional | `""` | Vision reasoning effort override (`""` for model default, or `minimal`). |
| `MAX_ENTRY_AMOUNT` | Optional | `100000.00` | Business logic boundary for maximum single transaction amount. |

