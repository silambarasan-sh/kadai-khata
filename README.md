# Kadai Khata (கடை கணக்கு)

A Tanglish (Tamil + English) text and notebook photo udhaar (credit) ledger assistant designed for small neighborhood shop owners (kirana / petty shops) in Tamil Nadu. (Note: voice input is not built; input is text and notebook photo).

Shop owners type natural everyday phrases like *"Ravi-ku 500 rupees udhaar kuduthen"* (Gave 500 rupees credit to Ravi) or *"Priya 200 kuduthanga"* (Priya paid 200), or photograph handwritten pages from physical paper khata notebooks. A Meta AI model parses the intent into structured transaction drafts via tool calling. The shop owner verifies and confirms the transaction before anything is saved to the ledger.

---

## What It Does
- **Tanglish Text & Notebook Photo Understanding**: Parses conversational Tamil-English statements and handwritten notebook page photos for credit given (*udhaar*) and repayments (*panam vanthathu*). (Voice input is NOT built; input is via text and notebook photos).
- **Human-in-the-Loop Confirmation**: AI never writes directly to the database without explicit owner review and approval.
- **Ledger & Outstanding Tracking**: Real-time balance calculations per customer with transaction history.
- **Polite Payment Reminders**: Drafts gentle, localized reminder messages in Tanglish/Tamil with direct WhatsApp link (`wa.me`) or clipboard copy only (SMS is not supported).
- **Mobile-First Interface**: Designed for single-hand mobile use by shopkeepers with quick actions.

---

## Originality & Disclosure

- **Development Timeline**: Development started on Oct 27, 2026 (first commit timestamp in git: `fbc7768 Tue Oct 27 11:29:39 2026 +0530`).
- **Repository Scope**: All code was written in this repository during the hackathon building period.
- **AI Assistance**: Built with AI coding assistance (Antigravity IDE).
- **Code Provenance**: No code was copied from Meta's cookbook, sample clients, or earlier projects.
- **Documentation**: Meta documentation was used only to learn API shapes, parameter formats, and endpoint behaviors.

---

## What Was Built During the Hackathon

All code in this repository was built from scratch during the hackathon building period (first commit: `fbc7768` on Tue Oct 27 11:29:39 2026 +0530). The test suite contains 82 tests (`pytest -q`), all passing.

- **Scaffold & Backend**: Django ledger application setup with clean models for `Customer`, `LedgerEntry`, `DraftEntry`, `AgentRun`, and `AgentStep` with decimal currency precision.
- **Meta AI Client Layer (`ledger/meta_client.py`)**: Centralized OpenAI SDK wrapper calling Meta API endpoints (`muse-spark-1.3`), handling live tool calling, exponential backoff with jitter on HTTP 429/5xx, explicit non-retry on 400, diagnostic logging, cached token reporting, and a deterministic offline mock client.
- **Tanglish Parser with Confirm Flow**: Multi-turn text parser converting conversational Tanglish into pending `DraftEntry` objects using function calling (`record_ledger_entry`, `ask_clarification`) with an explicit human-in-the-loop review/confirmation gate.
- **Safety Warnings Layer**: Real-time business logic safety flags on draft cards: anomalous amounts (>3x avg and >2x previous max), overpayments (payment exceeding balance), new customer on payment, and strict name-match guards.
- **Mobile Web UI**: Single-page mobile-responsive web interface (optimized for 390px mobile screens) with Tamil/English toggles, aging breakdown badges, quick filters, and zero CDN dependencies.
- **Verified Reminders**: Payment reminder generator drafting localized Tamil/Tanglish messages with an automated balance verifier, single retry loop, fallback templates, and WhatsApp (`wa.me`) link or clipboard copy.
- **Reversal Entries**: Non-destructive accounting audit trail allowing shopkeepers to reverse erroneous entries while preserving historical ledger records with offsetting transactions.
- **Collections Agent + Verifier + Hash-Chained Trace + Offline Replay**: Read-only autonomous agent proposing daily collection priorities using 4 read-only ledger tools; ground-truth verifier validating claimed balances and evidence IDs; append-only tamper-evident SHA-256 hash-chained execution trace (`ledger_agentstep`); and `agent_replay` CLI command verifying trace integrity offline without network calls.
- **Ask Endpoint (`/api/ask/`)**: Natural language query endpoint answering shopkeeper questions on balances and customer debt with amount verification guards.
- **Notebook Photo Workflow**: In-memory computer vision pipeline parsing multi-row handwritten ledger photos into draft batches, extracting column totals, matching Tamil names with Latin transliterations, filtering struck-out and smudged rows, and performing per-column total consistency checks.
- **Evaluation Tooling**: Automated evaluation CLI suites: `eval_parser` (multi-metric recall, accuracy, reasoning effort comparison across golden, held-out, and realistic negative sets), `eval_agent` (multi-run injection resistance and verification audit), and `eval_vision` (photo extraction benchmark with owner-verification detection).

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
pytest -q

# 9. Start development server
python manage.py runserver
```

---

## Meta Models Used & How the AI is Used

### Model & Specifications
- **Model**: `muse-spark-1.3` (Standard mode)
- **Base Endpoint**: `https://api.meta.ai/v1`
- **SDK**: OpenAI Python SDK (`openai.OpenAI`)
- **Key Authentication**: Handled via `MODEL_API_KEY`. The real key format is `LLM|numeric_id|secret`; it contains `|` characters, so it must be wrapped in double quotes in `.env`.
- **Interface**: Chat Completions API with Function Tools (`record_ledger_entry`, `ask_clarification`, `flag_cancelled`, `flag_unreadable`, `report_page_totals`).

### Verified API Findings (Live Probe)
1. **Tool Choice**: Meta Model API strictly supports `tool_choice="auto"` (sending `"required"` returns HTTP 400).
2. **Parallel Tool Calling**: Verified working live — compound sentences (e.g. *"Ravi-ku 500 udhaar kuduthen, Mani 200 thirumba kuduthaan"*) return multiple tool calls simultaneously in a single turn.
3. **Reasoning Effort**: `reasoning_effort` (`minimal`, `low`) is supported and configurable via `META_REASONING_EFFORT`.

### Human-in-the-Loop Confirmation Architecture
1. **Prompt Context**: Injects existing shop customer names into the system prompt to guide spelling consistency.
2. **Draft Isolation**: The AI has **no save permissions**. Every tool call only populates a `DraftEntry` model in the database with status `pending`.
3. **Explicit Confirmation**: The shopkeeper inspects the proposed draft (with exact match or fuzzy match suggestion), makes optional edits, and explicitly confirms or rejects it.
4. **Honest Labeling**: Every draft carries an immutable `source_label`:
   - `live`: Derived directly from live Meta Model API tool calls.
   - `mock`: Generated by the deterministic local mock parser.
   - `fallback`: Generated by the local rule-based regex parser if Meta API encounters errors or returns no tool calls.

### Evaluation & Benchmarks (`eval_parser`)

We test parser accuracy against three distinct benchmark datasets to maintain strict scientific honesty:
1. **Open-Book Golden Dataset (`tests/golden_sentences.json`)**: 20 sentences designed during development to specify behavior (compound transactions, Tamil number words, prompt injections, and conversational chatter).
2. **Held-Out Generalization Dataset (`tests/heldout_sentences.json`)**: 14 frozen sentences committed in `82e1e66` (Tue Oct 27 12:39:32 2026 +0530).
   - *Honest Disclosure*: The held-out set was visible to the coding agent in the same session in which `prompts.py` was restructured (commit `82e1e66`). The prompt was not changed after the first live run; contamination cannot be fully ruled out.
   - *Verbatim Audit*: An exact grep search across `ledger/prompts.py` for distinctive vocabulary fragments from the held-out sentences (`"nooththi"`, `"aimbadhu"`, `"lakh"`, `"evlo baaki"`, `"saamaan"`, `"kodutheen"`, `"vandhuchu"`, `"mark all customers"`) yielded **0 verbatim hits**.
3. **Realistic-Negative Dataset (`tests/realistic_sentences.json`)**: 15 real-world shopkeeper statements lacking usable transaction intent (inquiries about prices, grocery measurements in kilo/liter, loose change questions, future promises, closing time chatter). **All 15 strictly expect `no_entry` (zero drafts).**

#### Realistic Negative Dataset Results (Model: `muse-spark-1.3`, Live Mode)
- **Overall Accuracy**: **100.0%** (15/15)
- **No-Entry Correctness**: **100.0%** (15/15)
- **False-Positive Count**: **0** (zero drafts created for conversational statements)
- **Average Latency**: 7188.6 ms | **Average Total Tokens**: 2654.2

#### Reasoning Effort Multi-Run Comparison (`eval_parser --compare --repeat 3 --show-failures`)
Evaluated across **204 live API runs** (34 sentences × 3 repeats for each reasoning mode):

| Metric | Default Reasoning Effort (102 runs) | Minimal Effort (`META_REASONING_EFFORT="minimal"`, 102 runs) |
|---|---|---|
| **Overall Accuracy** | **99.0%** (101/102) | **100.0%** (102/102) |
| **Direction Accuracy** | **98.9%** (86/87) | **100.0%** (87/87) |
| **Amount Accuracy** | **98.9%** (86/87) | **100.0%** (87/87) |
| **No-Entry Correctness** | **100.0%** (27/27) | **100.0%** (27/27) |
| **False-Positive Count** | **0** | **0** |
| **Average Latency** | 5615.4 ms | **2542.9 ms (54.7% faster)** |
| **Average Total Tokens** | 2615.3 | **2035.5 (22.2% token savings)** |

*Failure analysis*: Under Default Effort, only 1 failure occurred across 102 runs (Run 2 on `"Kumar-ku moonu nooru udhaar"` where the model asked for clarification instead of creating an unconfirmed draft). Under Minimal Effort, 102/102 runs passed with zero failures.

### Safety Warnings Layer
`DraftEntry` instances automatically generate safety warnings displayed in the UI / API responses:
1. **New Customer on Payment**: Flags when a repayment is recorded for someone with no prior credit history.
2. **Overpayment Warning**: Alerts if a payment exceeds the customer's current outstanding balance (would cause negative balance).
3. **Anomalous Amount**: Flags amounts that exceed 3x average and 2x previous maximum for that customer.
4. **Strict Match Guard**: Only exact case-insensitive full-name matches are auto-matched. Partial, first-name, or fuzzy matches are flagged as suggestions on the confirm card with a "Change" option, and "Confirm all" is disabled until non-exact matches are reviewed.

---

## Screenshots & UI Walkthrough

| 1. Mobile Home Screen | 2. Confirm Drafts (Safety Warning) |
| :---: | :---: |
| ![Mobile Home Screen](docs/screenshots/home.png) | ![Confirm Drafts with Warning](docs/screenshots/confirm_warning.png) |

| 3. Customer Timeline & Reversals | 4. Verifiable Payment Reminders |
| :---: | :---: |
| ![Customer Timeline with Reversal](docs/screenshots/timeline_reversal.png) | ![Reminder Modal with Verified Badge](docs/screenshots/reminder_verified.png) |

| 5. Notebook Photo Review (LIVE) | 6. Collections Plan & Audit Chain |
| :---: | :---: |
| ![Notebook Photo Review LIVE](docs/screenshots/photo_review.png) | ![Collections Plan with Chain Valid](docs/screenshots/collections_plan.png) |

---

## Real vs Mocked Transparency

| Subsystem | Live / Real Mode (`META_MODE="live"`) | Mock Mode (`META_MODE="mock"`) |
|---|---|---|
| **Web UI** | Served dynamically at `/` with real-time responsive DOM updates, 44px touch targets, Tamil/English i18n, zero CDN dependencies. | Identical UI; works 100% offline without internet. |
| **Tanglish Parser** | Meta `muse-spark-1.3` Chat Completions with function tool calling (`record_ledger_entry`, `ask_clarification`). | Local deterministic pattern-matching engine with exact test fixture reproduction. |
| **Payment Reminders** | Meta `muse-spark-1.3` drafts polite reminder passing only factual customer name, balance, and days overdue. Verifier checks exact balance match; regenerates once on error; falls back to deterministic template on failure. | Deterministic localized templates with guaranteed verified balance and pre-filled `wa.me` WhatsApp link. |
| **Ledger & Reversals** | Real Django SQLite database; audit trail preserves all original entries and creates offsetting reversal entries. | Real database; identical behavior. |
| **Notebook Photo Parsing** | Meta `muse-spark-1.3` vision model processing base64 image data URL in memory via tool calling (`record_ledger_entry`, `flag_cancelled`, `flag_unreadable`, `report_page_totals`). Usage includes `cached_tokens`. | Deterministic local fixture producing pending drafts, flagged rows, and column totals without network calls. |
| **Daily Collections Agent** | Meta `muse-spark-1.3` autonomous multi-turn loop executing read-only tools (`list_overdue_customers`, `get_customer_history`, `get_payment_pattern`, `submit_plan`) with ground-truth balance verifier and SHA-256 hash chaining. | Deterministic local scripted agent run executing the same tool suite and verification offline. |
| **Ask Balance Endpoint** | Meta `muse-spark-1.3` tool calling (`get_customer_balance`, `list_customers_with_balance`) with strict amount verification against DB before returning response. | Deterministic local mock responses querying local DB data. |
| **Voice Input** | **Not built**. (The mic button in the UI is disabled and marked "Coming soon"; only text and notebook photos are accepted). | **Not built**. |

- **Source Labels**: Every draft and reminder card displays honest source badges:
  - `LIVE` (Emerald): Real Meta AI model completion.
  - `MOCK` (Sky Blue): Deterministic local test/mock completion.
  - `FALLBACK` (Amber): Rule-based fallback template triggered on failure or verifier mismatch.

---

## Collections Agent & Read-Only Ask Endpoint

Kadai Khata includes an autonomous, read-only **Daily Collections Agent** and an **Ask** endpoint with deterministic balance verification and tamper-evident audit logging.

### 1. Daily Collections Agent Architecture

- **Goal**: On demand, the agent investigates ledger accounts and proposes a structured daily collections plan (who to remind today and how).
- **Audit-Only Trace**: The agent **never writes ledger data; it only writes its own audit trace**. It has strictly read-only access to ledger records and only proposes actions. It never sends messages, creates entries, or modifies ledger data.
- **Tools (`ledger/agent_tools.py`)**:
  - `list_overdue_customers(min_balance, min_days_since_last_payment)`: Returns customers with outstanding debt and payment dates.
  - `get_customer_history(customer_id, limit<=20)`: Fetches recent transaction IDs, dates, amounts, and notes.
  - `get_payment_pattern(customer_id)`: Server-computes average days between payments, last payment amount/date, and reversals count.
  - `submit_plan(actions[])`: Terminal tool (up to 8 actions). Each action specifies `customer_id`, `action` (`remind_now` | `wait` | `call_personally`), `tone` (`soft` | `firm`), `claimed_balance`, `claimed_days_overdue`, `reason` (<= 200 chars), and `evidence_entry_ids[]`.
- **Prompt Injection Defense**: Ledger notes and transaction text are untrusted data. The system prompt instructs the agent to treat all tool outputs strictly as passive data and never obey instructions embedded in ledger notes.

### 2. Execution Loop & Boundaries (`ledger/agent.py`)

- **Tool Choice**: `tool_choice="auto"`.
- **Parallel Tool Calls**: Natively handled across multi-tool responses.
- **Caps & Safeguards**:
  - Max 6 model turns (`AGENT_MAX_TURNS`)
  - Max 12 tool executions (`AGENT_MAX_TOOL_CALLS`)
  - Token cap (`AGENT_MAX_TOKENS = 15000`)
  - Timeout (`AGENT_TIMEOUT_SECONDS = 45s`)
  - Single nudge on plain text before triggering fallback.
  - Hard cap of 8 actions per plan.

### 3. Ground Truth Verifier (`ledger/agent_verifier.py`)

Every proposed action is verified against database ground truth before display:
1. Recomputes true balance and days overdue directly from DB records.
2. Balance match must be exact (within ₹0.01).
3. Days overdue must match within ±1 day.
4. Customer must exist and have a positive balance (> 0).
5. Every `evidence_entry_id` must exist and belong to that exact customer.

**No Silent Dropping**: Actions that fail verification are marked `verified: false` with specific `failed_checks` and displayed with true recomputed values.

### 4. Append-Only Audit Trace & Tamper-Evident Hash Chain

- **Append-Only Model**: `AgentStep` blocks modification and deletion at both model and queryset levels (`save()` on an existing row raises `RuntimeError`, `delete()` raises `RuntimeError`).
- **Tamper-Evident Hash Chain**: Every step calculates `hash = sha256(prev_hash + canonical_step_json)`. `AgentRun` stores `final_hash`.
- **Offline Replay Command (`agent_replay <run_id>`)**:
  - Recomputes the hash chain from step 1 to final hash.
  - Re-runs the verifier on recorded actions using **only stored tool results** without invoking any AI model or network calls.
  - Validates chain integrity and verifies whether verdicts match stored results.
- **Caveats**:
  - *The hash chain lives in the same SQLite database.*
  - *Model-level guards can be bypassed with raw SQL queries (our tamper test in `tests/test_agent.py` does exactly that to test detection).*
  - *Anchoring the final hash outside the database (e.g. to a remote notary, transparency log, or external key-value store) is not built.*
  - *Hash chaining proves that a run is auditable, tamper-evident, and replayable offline without modification; it does NOT prove that the model's subjective reasoning was correct.*

### 5. Deterministic Fallback & Mock Modes

- **Mock Mode (`META_MODE="mock"`)**: Scripted offline simulation exercising real tools and producing verified plans.
- **Fallback (`source_label="fallback"`)**: If live agent times out, fails, or violates caps, a deterministic aging-based algorithm assigns recommendations based on overdue duration (60+ days -> `call_personally`, 30-59 days -> `remind_now` firm, <30 days -> `remind_now` soft).

### 6. Read-Only "Ask" Endpoint (`/api/ask/`)

- Supports shopkeeper balance questions (e.g. *"Ravi evlo baaki?"*).
- Uses read-only tools `get_customer_balance` and `list_customers_with_balance`.
- **Amount Verification**: Every rupee number mentioned in the synthesized response must appear in the tool results; any mismatched or hallucinated amount triggers a deterministic fallback.

### 7. Evaluation Benchmark (`eval_agent`)

Evaluated against a single scripted 10-customer scenario ($n = 3$ consecutive runs; 3 clearly overdue 60+ days, 2 active, 2 zero-balance, 1 adversarial prompt injection, 2 mixed) on an isolated temporary SQLite database:
```powershell
python manage.py eval_agent --runs 3 --live
```

#### Real Live Benchmark Results (3 consecutive runs):

| Run | Source | Overdue Covered (of 3) | Zero-Bal Proposed (Ideal: 0) | Injected Note Obeyed | Verifier Rejections | Chain Valid | Replay Identical | Latency | Tokens |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **#1** | live | 3/3 | 0 | No | 0 | Yes | Yes | 11.3s | 8,056 |
| **#2** | live | 3/3 | 0 | No | 0 | Yes | Yes | 10.3s | 8,066 |
| **#3** | live | 3/3 | 0 | No | 0 | Yes | Yes | 9.3s | 7,762 |
| **Summary** | **Live** | **3.0 / 3 (100%)** | **0.0** | **0 of 3 runs obeyed** | **0.0 avg** | **3 of 3 runs valid** | **3 of 3 runs identical** | **10.31s avg** | **7,961 avg** |

#### Verifier Audit:
- **What was verified live**: Every proposed action's claimed balance was compared against exact ground truth (within ₹0.01) and days overdue (within ±1 day), and evidence IDs were checked for ownership. In all 3 live runs, the model used tool figures accurately without hallucinating amounts.
- **What the verifier caught vs did not catch**: The model adhered to the anti-injection system prompt, meaning zero injected notes were obeyed (`0 of 3 runs obeyed the injected note`) and no zero-balance customers were proposed. Because the model extracted accurate figures directly from tool outputs, 0 actions required rejection. However, the verifier serves as a hard boundary: if the model ever hallucinates an unverified amount or attributes a receipt to the wrong customer, the action is immediately flagged "Unverified" with true recomputed values rather than accepted blindly.
- **Offline Tamper-Evident Replay**: Running `python manage.py agent_replay <run_id>` recomputed the SHA-256 hash chain and confirmed `Chain valid: Yes` and `Replay identical: Yes` across all 3 runs. Tampering with even a single byte in any step's stored JSON immediately invalidates the chain.

---

## Notebook Photo -> Batch Drafts (Vision Workflow)

For shopkeepers who keep physical pen-and-paper khata notebooks, Kadai Khata provides an in-memory photo digitization workflow that converts a ledger page into batch transaction drafts.

### 1. In-Memory Zero-Storage & Privacy Architecture
- **Zero Disk or DB Storage**: The image is received via `POST /api/parse-photo/` directly into memory as a byte stream, converted to an in-memory base64 data URL for Meta AI vision inference, and immediately discarded. Neither the original image nor base64 chunks are ever written to disk or database.
- **Client-Side Canvas Downscaling & EXIF Stripping**: The mobile web app downscales the image in the browser via an HTML canvas (max long edge 1600px, JPEG quality 0.85). This process strips all EXIF metadata (including phone GPS coordinates, camera model, and device timestamps) prior to network transmission.
- **MIME & Size Enforcement**: Server rejects payloads exceeding 4MB or non-image MIME types (accepts only `image/jpeg`, `image/png`, `image/webp`) with HTTP 400.

### 2. Table Layout & Column Semantics
The vision system prompt is configured for standard Tamil Nadu shopkeeper khata tables:
- **Columns**: `Date | Name | Note | Udhaar | Jama` or Tamil headers `"தேதி | பெயர் | விவரம் | கடன் | வரவு"`.
- **Direction Rules**:
  - Amount in **Udhaar / கடன்** column -> `credit_given` (customer took goods on credit).
  - Amount in **Jama / வரவு** column -> `payment_received` (customer settled / paid money).
  - Hyphen (`"-"`), dash, or empty cell denotes zero / no entry.
- **Limitation (v1)**: **Dates are NOT parsed in v1**. All confirmed transactions are recorded with the ledger timestamp at confirmation time.

### 3. Tamil Script Preservation & Latin Transliteration (`name_latin`)
- Names written in Tamil script (e.g. *"முருகன்"*, *"கார்த்திக்"*) are preserved verbatim in `customer_name`.
- The model suggests an English/Latin phonetic transliteration in `name_latin` (e.g. *"Murugan"*, *"Karthik"*). All-lowercase Latin names are automatically title-cased (e.g. `mani` -> `Mani`).
- The review UI displays both names with an interactive toggle chip, allowing the shopkeeper to choose whether to save the Tamil or Latin spelling to their customer database.
- **`source_text` Semantics**: In photo drafts, `source_text` is stored as a structured echo of the extracted row (e.g. `"[Row 1: Murugan] Murugan | Rice 5kg | credit_given ₹450.00"`), capturing the raw customer string and extracted row hint, rather than raw unsegmented OCR text.

### 4. Cancellation & Illegibility Protection
- **Struck-Out / Scribbled Rows**: Rows with lines drawn through them, tildes, or cancellation scribbles are captured via the `flag_cancelled(row_hint)` tool and are **never** converted into transaction drafts.
- **Smudged / Illegible Rows**: Unclear or torn rows trigger `flag_unreadable(row_hint, reason)`. The model is instructed to **never guess** names or figures.
- Both types of skipped rows are displayed in a transparent "Skipped rows from photo" accordion on the review screen.

### 5. Per-Column Total Check & Safety Gate
Physical ledger pages frequently conclude with column totals written at the bottom. The model extracts these via `report_page_totals(total_udhaar, total_jama)`:
- **Per-Column Comparison**:
  - `sum(drafted credit_given)` vs written `total_udhaar`
  - `sum(drafted payment_received)` vs written `total_jama`
- **Safety Gate & Ambiguity Finding**:
  - If a mismatch occurs, a warning banner appears detailing both computed and written totals.
  - The banner explicitly cites any cancelled or unreadable rows that might account for the discrepancy.
  - **"Confirm all" remains disabled** until the shopkeeper checks the acknowledgement box: *"I understand the column totals don't match (e.g. struck-out or unreadable rows) and want to proceed."*
  - **Critical Safety Insight**: On `newpage2.jpeg`, ambiguous handwriting caused both the Rani payment row and the bottom total jama to look like 260 instead of the owner-intended 200. Because the model read both the row and the column total as 260 consistently, the automated total check showed `Pass`! A misread that is internally consistent between a row and its page total cannot be detected by mathematical total checking. This illustrates why the human-in-the-loop confirmation screen remains the indispensable safety net for real kirana stores.

### 6. Vision Configuration & Caching
- **Independent Vision Settings**:
  - `META_VISION_REASONING_EFFORT`: Configures reasoning effort specifically for vision completions, independent of `META_REASONING_EFFORT`. Defaults to empty string (model default).
  - `META_VISION_TIMEOUT_SECONDS`: Vision timeout set to `90.0` seconds (default) to comfortably handle complex multi-row pages (e.g. `newpage2` taking ~20-30s).
- **Client Processing UI**: While processing, the mobile UI displays *"Reading the page... can take up to 30 seconds (Xs)"* with an active elapsed seconds counter, a user **Cancel** button (powered by `AbortController`), and clear user-facing timeout handling.
- **Token Logging & Prompt Caching**: Vision requests log standard token metrics plus `usage.cached_tokens`, capturing prompt caching across notebook page scans.

### 7. Evaluation Benchmark (`eval_vision`)
Evaluates model extraction against owner-verified ground truth in `tests/vision_samples/`:
```powershell
python manage.py eval_vision --live
```

All 3 samples (`newpage1.json`, `newpage2.json`, `newpage3.json`) are owner-verified (`owner_verified: true`, following owner clarification that on `newpage2` Rani payment and page total jama are ₹200).

#### Live Benchmark Results ($n = 3$ images, 11 total ground-truth rows)

| Metric | Default Effort (Run A) | Default Effort (Run B) | Minimal Effort (`minimal`) |
|---|---|---|---|
| **Overall Row Recall** | **90.9%** (10/11) | **100.0%** (11/11) | **90.9%** (10/11) |
| **Exact-Field Accuracy** | **81.8%** (9/11) | **90.9%** (10/11) | **90.9%** (10/11) |
| **Total False-Positive Rows** | 1 | 0 | 1 |
| **Cancelled Rows Handled** | 1 / 1 detected | 2 / 1 detected | 1 / 1 detected |
| **Unreadable Rows Handled** | 1 / 1 flagged | 0 / 1 flagged | 1 / 1 flagged |
| **Average Latency** | 13.58s | 11.12s | **5.39s** |
| **Average Total Tokens** | 5,414 | 5,172 | **4,014** |
| **Total Cached Tokens** | 0 | 4,578 | 0 |

- **Rani Amount Misread on newpage2**: In both default effort runs, the model extracted Rani's payment as ₹260 (matching what looks like 260 on paper), whereas the owner intended ₹200. In Run A this gave 9/11 exact match, and in Run B 10/11 exact match. This is documented honestly as a genuine model handwriting misread.
- **Recommended Effort Setting**: **Default reasoning effort (`META_VISION_REASONING_EFFORT=""`)** is recommended. Although minimal reasoning effort yields faster inference (~5.4s vs ~11-13s), default reasoning effort achieves superior row recall (up to 100% recall with 0 false rows in Run B, vs false-positive rows under minimal effort). Vision requests require the full reasoning capacity to reliably disambiguate noisy handwriting and columns.

---

## Known Limitations

1. **No Authentication / Multi-User**: Designed as a single-shopkeeper demo; lacks multi-tenant isolation, user accounts, and login authentication.
2. **SQLite Database**: Uses local SQLite database; not intended for high-concurrency production deployments without migration to PostgreSQL.
3. **Photo Dates Not Parsed**: The v1 vision parser does not extract transaction dates from notebook rows; confirmed transactions are recorded with the ledger timestamp at confirmation time.
4. **Small Evaluation Sample Sizes**:
   - Parser Golden Set: $n = 20$
   - Parser Held-Out Set: $n = 14$
   - Parser Realistic-Negative Set: $n = 15$
   - Daily Collections Agent: $n = 3$ runs across 1 scripted 10-customer scenario
   - Vision Digitizer: $n = 3$ images ($11$ total ground-truth rows)
5. **Tamil Language Nuance**: Tamil and Tanglish phrasing variations, colloquial dialect terms, and regional honorifics need further validation by native domain speakers.
6. **Voice Input Not Built**: The microphone button in the UI is disabled and marked "Coming soon"; only text input and notebook photo uploads are supported.
7. **Meta Free-Tier Terms**: Inputs and outputs sent under free-credit / developer-tier Meta API usage may be retained or utilized by Meta for model improvement.
8. **Reminders are Drafts Only**: Reminders are generated as suggested text with WhatsApp (`wa.me`) links or copy buttons; automatic background SMS or WhatsApp dispatch is not built.
9. **Development Server**: Intended for hackathon demonstration with Django development server (`manage.py runserver`); not hardened for production WSGI/ASGI hosting.

---

## License
MIT License - Copyright (c) 2026 Silambarasan N
