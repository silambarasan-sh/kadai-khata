# Kadai Khata (கடை खाता / கடை கணக்கு)

A Tanglish (Tamil + English) voice/text udhaar (credit) ledger assistant designed for small neighborhood shop owners (kirana / petty shops) in Tamil Nadu.

Shop owners speak or type natural everyday phrases like *"Ravi-ku 500 rupees udhaar kuduthen"* (Gave 500 rupees credit to Ravi) or *"Priya 200 kuduthanga"* (Priya paid 200). A Meta AI model parses the intent into a structured transaction draft via tool calling. The shop owner verifies and confirms the transaction before anything is saved to the ledger.

---

## What It Does
- **Tanglish Speech & Text Understanding**: Parses conversational Tamil-English statements for credit given (*udhaar*) and repayments (*panam vanthathu*).
- **Human-in-the-Loop Confirmation**: AI never writes directly to the database without explicit owner review and approval.
- **Ledger & Outstanding Tracking**: Real-time balance calculations per customer with transaction history.
- **Polite Payment Reminders**: Drafts gentle, localized reminder messages in Tanglish/Tamil for WhatsApp or SMS.
- **Mobile-First Interface**: Designed for single-hand mobile use by shopkeepers with quick actions.

---

## Quick Setup

### Prerequisites
- Python 3.11+ (tested on Python 3.14)
- Git

### Installation (PowerShell on Windows)
```powershell
# 1. Clone repository
git clone https://github.com/silambarasan-sh/kadai-khata.git
cd kadai-khata

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment variables
Copy-Item .env.example .env

# 5. Run database migrations
python manage.py migrate

# 6. Seed demo data (8 Tamil Nadu customers with 40 realistic transactions)
python manage.py seed_demo_data

# 7. Check Meta AI model connectivity (in mock or live mode)
python manage.py meta_check

# 8. Run test suite
pytest

# 9. Start development server
python manage.py runserver
```

---

## What Was Built During the Hackathon
- **Django Ledger Backend**: Clean models for `Customer` and `LedgerEntry` with decimal precision for currency.
- **Core Ledger Services**: Balance computation, customer resolution, amount bounds validation, and idempotent seeding.
- **Meta AI Client Layer (`ledger/meta_client.py`)**:
  - The single centralized entry point for calling Meta models via the OpenAI Python SDK.
  - Exponential backoff with jitter on HTTP 429 (rate limits) and 5xx (server errors).
  - Explicit non-retry on HTTP 400 (bad requests).
  - Clear error reporting for HTTP 401 (invalid/missing key) and 404 (model/endpoint not found).
  - Fully deterministic offline mock client for zero-cost testing and continuous integration.
- **Management Commands**:
  - `seed_demo_data`: Seeds 8 Tamil Nadu customers and 40 realistic transactions over 60 days (idempotent).
  - `meta_check`: Diagnostic utility to verify Meta API connection, model ping, token counts, and latency without leaking secrets.
- **Test Suite**: Comprehensive pytest suite covering models, service logic, bounds validation, idempotency, and Meta client behaviors (mock, live, 401, 400, 429 backoff).

---

## Meta Models Used
- **Model**: `muse-spark-1.3` (Standard mode)
- **Base Endpoint**: `https://api.meta.ai/v1`
- **SDK**: OpenAI Python SDK (`openai.OpenAI`)
- **Key Authentication**: Handled via `MODEL_API_KEY`. The real key format is `LLM|numeric_id|secret`; it contains `|` characters, so it must be wrapped in double quotes in `.env`.
- **Interface**: Chat Completions API with function calling / tools.
- **Usage**:
  1. **Intent & Transaction Parameter Extraction**: Extracts `customer_name`, `kind` (`credit_given` or `payment_received`), `amount`, and `note` from Tanglish sentences.
  2. **Payment Reminder Drafting**: Generates context-aware, respectful Tamil/Tanglish payment reminders.

---

## Real vs Mocked & Limitations (Transparency)
- **Real in Current State**:
  - Django ORM models, migrations, and SQLite storage.
  - Core business logic: customer resolution, balance math, validation limits.
  - Idempotent demo data generator with realistic Tamil Nadu names and amounts.
  - Meta client implementation with real retry backoff and error translation.
- **Mock Mode**:
  - `META_MODE=mock` by default in `.env.example` so tests and local runs never consume API tokens or fail without credentials.
  - Results transparently flag their source:
    - `"live"`: Returned directly from the Meta Model API.
    - `"mock"`: Deterministic local mock response (useful for tests and offline dev).
    - `"fallback"`: Rule-based fallback if connectivity fails.
- **Limitations**:
  - Does not connect to banking UPI APIs for automated bank reconciliation (shop owner records manually).
  - Single shop owner ledger per database instance (no multi-tenant auth in initial indie track scope).

---

## License
MIT License - Copyright (c) 2026 Silambarasan N
