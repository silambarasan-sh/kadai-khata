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
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-1}"
exec gunicorn kadai_khata.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --threads 4 \
    --worker-class gthread \
    --timeout 120 \
    --max-requests 200 \
    --max-requests-jitter 20 \
    --access-logfile - \
    --error-logfile -
```

> [!IMPORTANT]
> **Why 1 Worker is Safer on Render's 512 MB Free Instance**:
> - **Memory Ceiling**: Render free-tier instances have a strict 512 MB RAM ceiling. Crossing this limit causes the Linux kernel OOM (Out Of Memory) killer to immediately terminate the container.
> - **Worker Duplication Avoidance**: Each Gunicorn process duplicates Python runtime memory (~45–55 MB base RSS). Running 2 workers immediately consumes ~110 MB before processing any traffic. When heavy operations occur (such as Pillow decoding camera photos up to 40 megapixels or buffering audio files), concurrent worker spikes can easily cross 512 MB.
> - **Threaded I/O Concurrency**: With a single worker process (`WEB_CONCURRENCY=1`) and 4 `gthread` threads, all network-bound concurrency (waiting on Meta Model API or Baseten inference) runs across threads within a single memory footprint. This leaves >350 MB of free RAM headroom.
> - **Extended Timeout (120s)**: Complex multimodal vision inference (`/api/parse-photo/`) can take 20–30 seconds on large handwritten pages. The 120s timeout prevents premature worker termination.
> - **Request Recycling (`--max-requests 200 --max-requests-jitter 20`)**: Recycles the worker process after 200 requests (with random jitter to prevent thundering herds), returning fragmented heap memory and native C-library buffers back to the OS.

---

## 3. Verifying the Deployment & Process Uptime

Once deployed, probe the health endpoint:
```bash
curl -i https://<your-service-url>.onrender.com/healthz
```

Expected Response (`HTTP 200 OK`):
```json
{
  "status": "ok",
  "mode": "live",
  "uptime_seconds": 142.5
}
```

The `uptime_seconds` field reports the elapsed time since the Gunicorn master process started. If this number is low (e.g., < 60 seconds), the free instance recently woke up from spin-down or restarted.

---

## 4. Ephemeral Storage vs. Persistent Disks

> [!NOTE]
> **Free-Instance Ephemeral SQLite Limitation**:
> Render free-tier instances run on ephemeral container filesystems. When the free service spins down after 15 minutes of inactivity or restarts during deploys, the SQLite database file (`db.sqlite3`) resets to its initial state.
> 
> On startup, `python manage.py seed_demo_data --if-empty` automatically re-populates the 8 fictional Tamil Nadu demo customers and 40 transactions whenever the database is empty.
> 
> **Option for Persistent Storage (Paid Plan)**:
> In production environments requiring persistent SQLite storage without an external PostgreSQL database, attach a Render Disk:
> 1. In Render Dashboard &rarr; Service &rarr; **Disks**, add a disk mounted at `/var/data` (1 GB size).
> 2. Set environment variable `DATABASE_PATH="/var/data/db.sqlite3"`.
> 
> *(Do not enable persistent disks on the free demo instance, as Render Disks require a paid plan).*

---

## 5. Structured Server Logging in Render Logs

Every `/api/` request outputs exactly one structured JSON line to stdout with the prefix `[API]`. In addition, Gunicorn configuration and initial RSS memory are logged once at startup with `[STARTUP]`.

### How to Read Logs in the Render Dashboard:
1. Navigate to **Render Dashboard** &rarr; Your Service &rarr; **Logs**.
2. Filter by `[API]` to inspect request flow, latency, and status:
   ```json
   [API] {"method": "POST", "path": "/api/parse/", "status": 200, "duration_ms": 48.2, "error_class": null, "engine": "meta/muse-spark-1.3", "source_label": "live"}
   ```
3. Filter by `rss_mb` to monitor resident set size memory after photo uploads and voice transcriptions:
   ```json
   [API] {"method": "POST", "path": "/api/parse-photo/", "status": 200, "duration_ms": 1420.5, "error_class": null, "engine": "meta/muse-spark-1.3", "source_label": "live", "rss_mb": 56.4}
   ```
4. Filter by `[STARTUP]` to verify Gunicorn settings when a container boots:
   ```json
   [STARTUP] {"event": "startup", "gunicorn": {"workers": 1, "threads": 4, "timeout": 120, "max_requests": 200, "max_requests_jitter": 20}, "rss_mb": 38.2}
   ```

**Privacy Guarantee**: Request bodies, customer names, rupee amounts, and API keys are strictly excluded from all log lines.

---

## 6. Complete Environment Variables Reference

All environment variables use placeholder values below. Never commit real keys.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DJANGO_DEBUG` | Optional | `False` | Must be `False` for production deployments. |
| `DJANGO_SECRET_KEY` | Required if not debug | `[GENERATE_SECRET_KEY]` | Cryptographic secret key for session and CSRF signing. Fails fast if missing when `DJANGO_DEBUG=False`. |
| `ALLOWED_HOSTS` | Required | `.onrender.com,localhost,127.0.0.1` | Comma-separated list of valid host headers. |
| `CSRF_TRUSTED_ORIGINS` | Required | `https://*.onrender.com` | Comma-separated list of trusted origins for CSRF protection. |
| `DJANGO_ENABLE_ADMIN` | Optional | `0` | Set to `1` to enable the `/admin/` route. Default `0` disables it in public demos. |
| `WEB_CONCURRENCY` | Optional | `1` | Number of Gunicorn worker processes (default 1 to fit 512 MB free tier). |
| `DATABASE_PATH` | Optional | `""` | Optional explicit path for the SQLite database (defaults to `BASE_DIR / db.sqlite3`). |
| `DEMO_MODE` | Optional | `1` | Enables public demo banner, hourly rate limits, and daily live budget tracking. |
| `DEMO_DAILY_LIVE_CALLS` | Optional | `300` | Global daily live Meta API request budget (resets at UTC midnight). |
| `DEMO_RATE_LIMIT_TEXT` | Optional | `20` | Maximum text parse / ask transactions per client IP per hour. |
| `DEMO_RATE_LIMIT_PHOTO` | Optional | `5` | Maximum notebook photo uploads per client IP per hour. |
| `DEMO_RATE_LIMIT_VOICE` | Optional | `10` | Maximum speech-to-text transcriptions per client IP per hour. |
| `DEMO_RATE_LIMIT_AGENT` | Optional | `3` | Maximum daily collections agent reviews per client IP per hour. |
| `DEMO_RATE_LIMIT_REMINDER` | Optional | `20` | Maximum reminder drafts per client IP per hour. |
| `VOICE_LANGUAGE_BIAS` | Optional | `"Tamil,English"` | Target language bias for Meta Muse Voice Transcribe. Comma-separated. |
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
| `META_PROVIDER` | Optional | `meta` | Inference backend provider: `meta` (Meta Model API) or `partner` (Baseten). |
| `PARTNER_BASE_URL` | Optional | `https://inference.baseten.co/v1` | Base URL for Baseten partner inference backend. |
| `PARTNER_MODEL` | Optional | `meta-models/muse-spark-open-1026` | Model identifier for Baseten Muse Spark Open backend. |
| `PARTNER_API_KEY` | Optional | `""` | Baseten API key. Required when using the Baseten backend. |
| `PARTNER_TIMEOUT_SECONDS` | Optional | `90.0` | Timeout in seconds for partner backend completions. |
| `MAX_ENTRY_AMOUNT` | Optional | `100000.00` | Business logic boundary for maximum single transaction amount. |
