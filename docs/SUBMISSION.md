# Hackathon Submission Drafts

This file contains the verified text drafts for the submission form. All figures, claims, and capabilities are backed by tests and benchmarks documented in [`docs/EVIDENCE.md`](EVIDENCE.md).

---

### Project Name
Kadai Khata (கடை खाता)

---

### One-Line Pitch (<= 120 characters)
AI credit ledger helping Tamil Nadu kirana owners digitize udhaar via Tanglish text, voice, and notebook photos.

---

### Track
Indie Track

---

### Problem Statement Chosen
**Build for Your World**: Small neighbourhood kirana and provision store owners across Tamil Nadu maintain daily customer credit (*udhaar* / கடன்) in physical paper notebooks. When notebooks get smudged, torn, or misplaced, disputes occur and shopkeepers lose hard-earned income. Existing accounting apps require cumbersome manual forms and English proficiency, alienating rural and semi-urban shopkeepers who speak colloquial Tanglish.

---

### Description (250 words)
In Tamil Nadu, neighbourhood kirana store owners extend daily credit (udhaar / கடன்) to familiar families. Today, this is recorded across paper notebooks using colloquial Tanglish, Tamil numerals, and scratch-outs. When notebooks tear, ink smudges, or customers dispute balances months later, shopkeepers lose income and trust.

Kadai Khata brings AI into the shopkeeper's real daily workflow without requiring them to become accountants. It supports three input modalities tailored to small stores: speaking rapid Tanglish phrases via Meta Muse Voice Transcribe, typing natural sentences like "Ravi-ku 450 udhaar groceries", or snapping a photo of an entire handwritten notebook page with Meta Muse Spark 1.3 vision.

Crucially, Kadai Khata enforces a strict "AI proposes, owner confirms" safety boundary. The AI never commits directly to the ledger. Every proposed entry appears on a mobile review slip with deterministic sanity checks: flagging repayments from unlisted customers, overpayments causing negative balances, and anomalous spikes compared to customer history. Handwritten photo extraction includes automated per-column total checks to catch missed rows before saving.

For daily operations, a verifiable collections agent analyzes aging customer balances, calculates overdue periods, and drafts polite bilingual WhatsApp reminders with verified amounts. Every step is recorded in a tamper-evident SHA-256 hash chain that can be audited offline. The entire application runs on mobile viewports with zero client-side dependencies, English and Tamil script switching, and in-memory processing guarantees where customer photos and voice bytes are never stored.

---

### How We Used Meta's Models (150 words)
We integrated three Meta models via OpenAI-compatible endpoints with strict domain separation:

1. **Meta Muse Spark 1.3**: Used as our primary text, reasoning, and vision engine. For natural Tanglish text input, it performs multi-action function calling to extract customer names, amounts, and credit/payment direction. In vision mode, it parses base64 handwritten notebook photos into structured ledger drafts while detecting smudges and crossed-out rows. In collections mode, it plans daily reminder workflows.
2. **Meta Muse Voice Transcribe**: Transcribes spoken Tanglish audio in memory, phonetic-grounded with dynamic customer keyword biasing.
3. **Meta Muse Spark Open (via Baseten)**: Integrated as an optional open-weights partner engine for text parsing, balance queries, and reminder drafting.

Empirically, tuning reasoning effort to minimal reduced latency by 54.7% (2542.9 ms vs 5615.4 ms) while maintaining 100.0% accuracy across our 49-sentence benchmark.

---

### What Was Built During the Hackathon (5 Bullets)
- **Tanglish Multi-Action Parser**: Built a function-calling parser using Meta Muse Spark 1.3 that extracts multiple simultaneous credit/payment actions from colloquial Tanglish phrases, backed by deterministic rule-based regex fallback and 100.0% accuracy on our 49-sentence benchmark ($n = 49$).
- **In-Memory Handwritten Notebook Digitizer**: Created a vision pipeline powered by Meta Muse Spark 1.3 that parses double-column kirana notebook pages into draft entries in memory, with automated per-column total checking, Tamil script preservation, and scratch-out row detection.
- **Voice Transcription with Local Keyword Biasing**: Implemented in-browser Web Audio recording and server-side transcription using Meta Muse Voice Transcribe, evaluated across 56 live API probe calls ($n = 4$ clips, 7 variants × 2 repeats) with shopkeeper-in-the-loop transcript review before sending.
- **Verifiable Collections Agent & Hash-Chain Audit**: Developed an autonomous collections agent that proposes prioritized repayment follow-ups, verified by deterministic python code against ground truth ledger state and logged in an append-only, tamper-evident SHA-256 hash chain with offline replay verification.
- **Mobile-First Zero-Build Application**: Delivered a clean mobile UI with live English/Tamil script switching, WhatsApp reminder deep-linking, non-destructive audit reversals, dual-engine runtime switching (Meta Model API vs Baseten), and 156 automated tests (142 offline + 14 browser E2E).

---

### Links Placeholders
- **GitHub Repository**: https://github.com/silambarasan-sh/Kadai-Khata
- **Live Demo Link**: https://kadai-khata.onrender.com
- **Demo Video**: [Link to public video added at submission]
- **X (Twitter) Post**: [Link to public X post added at submission]

---

### Open-Weights Note
Meta's open-weight model **Muse Spark Open (`meta-models/muse-spark-open-1026`)** hosted on Baseten's serverless infrastructure is supported as an optional inference backend engine for Tanglish text parsing, balance queries, and reminder drafting. In-memory notebook photo parsing and voice transcription require Meta's multimodal APIs. Both engines pass our identical 49-sentence benchmark with 100.0% accuracy and are selectable live via the engine dropdown in the app header.

---

### Final Submission Checklist
- [x] Public GitHub repository accessible with clean commit history
- [ ] Public video demonstration recorded and link attached
- [x] Live web deployment working in an incognito window: https://kadai-khata.onrender.com
- [x] Meta hackathon credits configured and verified live
- [ ] Public X (Twitter) post shared with demo link and hashtags

