# RegGuard AI — Agentic AI Compliance Investigator
**Nigeria CBN AML/CFT Compliance Automation**

RegGuard AI is an autonomous compliance agent designed to investigate flagged financial transactions across regulatory rules, transaction histories, and sanctions/PEP watchlists without hallucinating conclusions.

---

## Architecture Core: Plan → Act → Critique → Refine → Synthesize

When evidence is ambiguous, contradictory, or insufficient, RegGuard AI reformulates queries or escalates to a human compliance officer. It **never** fabricates a conclusion.

### Routing Rule Invariant
> `escalate` is only reachable via `synthesize`; `synthesize` is always visited before terminal state (`concluded` or `escalated`).

---

## Three Benchmark Scenarios & Dispositions

| Case | Scenario | Evidence Dynamics | State Machine Path | Disposition |
| :--- | :--- | :--- | :--- | :--- |
| **Case A** | Cash Structuring | Triplet cash deposits below statutory N5M aggregating to N5.5M in 25.5h | `plan` → `act` → `critique` → `synthesize` (0 retries) | `DRAFT_STR` |
| **Case B** | PEP Watchlist Match | High name similarity (0.87 / 1.0) but 33-year KYC DOB mismatch (1994 vs 1961) | `plan` → `act` → `critique` → `refine` → `act` → `critique` → `synthesize` → `escalate` (1 retry) | `ESCALATE_TO_OFFICER` |
| **Case C** | Temporal Contradiction | 2021 corporate deposit of N7.5M initially citing 2022 regulation (N5M limit) | `plan` → `act` → `critique` → `refine` (effective_before=2021-08-14) → `act` (2013 rules N10M limit) → `critique` → `synthesize` (1 retry) | `CLEAR_NO_SUSPICION` |

---

## Audit Memo & Cryptographic Ledger Drilldown (Day 9 Deliverables)

1. **Formal Compliance Audit Export Pipeline (`app/audit_memo.py`)**:
   - **Markdown Export (`generate_audit_memo_markdown`)**: Official compliance document structured under CBN AML/CFT Regulations 2022 & NFIU Suspicious Transaction Reporting guidelines. Formats executive summaries, statutory violation clauses, chronological evidence ledger blocks, and reviewing compliance officer sign-offs.
   - **Print-to-PDF Ready HTML Document (`generate_audit_memo_html`)**: Standalone printable letterhead document with official bank branding, responsive cryptographic evidence tables, and `@media print` styles for clean PDF export.
2. **FastAPI Export Endpoints (`app/server.py`)**:
   - `GET /investigations/{id}/audit_memo`: Structured JSON representation containing both Markdown and HTML exports.
   - `GET /investigations/{id}/export/markdown`: Streamed `.md` attachment file (`Content-Disposition: attachment; filename="cbn_audit_memo_{id}.md"`).
   - `GET /investigations/{id}/export/html`: Standalone browser-renderable HTML report with print-to-PDF controls.
   - `GET /investigations/{id}/claims/{claim_id}/verify`: Cryptographic verification endpoint validating canonical JSON serialization and SHA-256 integrity.
3. **Frontend Evidence Drilldown & Report Modals (`static/index.html`)**:
   - **Cryptographic Block Inspector Modal**: Triggered by clicking any block hash or "Inspect Block Proof". Displays untruncated claim ID, proposition text, status, supporting sources, `prev_hash`, `hash`, and the exact canonical JSON payload.
   - **Client-Side Live Web Crypto SHA-256 Recalculation**: Features an interactive "Verify Hash Now" button that independently hashes the canonical payload inside the browser sandbox using `window.crypto.subtle.digest('SHA-256')` to prove zero tampering.
   - **Interactive Audit Memo / STR Viewer Modal**: Triggered via "View Full Report / STR Audit Memo". Renders the full letterhead report in an isolated sandbox with one-click "Print / Save PDF" and "Download .MD" controls.

---

## Responsive 3-Column UI & Live SSE Integration (Day 8 Deliverables)

1. **Responsive Layout (`static/index.html`)**:
   - Replaced fixed 1280×720 viewport with a fluid, responsive Tailwind grid (`grid-cols-1 lg:grid-cols-12`).
   - Adapts cleanly from mobile viewports to ultrawide projection screens with independent column scroll areas and zero horizontal overflow.
2. **Live SSE Streaming Transitions**:
   - Native browser `EventSource` connection streaming real-time LangGraph transitions with zero WebSocket overhead.
   - Animated visual node stepper (`Plan` → `Act` → `Critique` → `Refine` → `Synthesize` → `Escalate`) with dynamic glowing status indicators.
3. **Cryptographic Evidence Ledger Block View (Column 2)**:
   - Displays append-only claim blocks with `prev_hash` and `hash` linkages.
   - Highlights superseded modern regulations (Case C) with clear audit explanations.
4. **Interactive Compliance Officer Decision Panel (Column 3)**:
   - Previews formal Draft STR, Clearance Certificate, or Escalation Dossier.
   - Allows compliance officers to enter audit remarks and submit determinations (`Approve STR`, `Clear Flag`, `Request EDD`, `Escalate Senior`).

---

## Deterministic Replay Engine & CACHED Mode (Day 7 Deliverables)

CACHED mode is **not** a video playback or static mockup. It executes the **real LangGraph state machine** and **real graph edges** with the network stubbed out.

1. **Deterministic Keying Algorithm (`core/replay_engine.py`)**:
   $$\text{fixture\_key} = \text{SHA256}(\text{node\_name} + \text{canonical\_json}(\text{inputs}))$$
   - Enforces byte-for-byte fidelity: changing even a single character in a prompt or schema changes the compound hash.
2. **Replay Store (`data/replay_fixtures/replay_store.json`)**:
   - Holds 10 schema-validated, tamper-checked interaction fixtures covering planning, critique evaluation, query reformulation, and synthesis across all three cases.
3. **Strict Mismatch Detection**:
   - If an unrecorded prompt is executed in CACHED mode, `CachedLLMProvider` throws an explicit `DeterministicReplayMismatchError`, preventing state drift or simulated hallucination.
4. **Zero-Network Execution**:
   - In CACHED mode, 100% of LLM calls hit local fixtures, while tool calls execute directly against local SQLite and local Qdrant vectors.

---

## Custom Transaction Input & Dynamic Case Evaluation

In addition to the pre-seeded benchmark scenarios (Cases A, B, and C), RegGuard AI supports **arbitrary custom transaction submissions**:
- **UI Trigger**: Click `"Custom Input"` in the top navigation bar or select `"★ Custom Input Transaction..."` from the case dropdown.
- **Form Inputs**: Customer Full Name, Entity Type (`INDIVIDUAL` / `CORPORATE`), Account Number, Transaction Amount in NGN, Channel / Type (`CASH_DEPOSIT`, `INWARD_TRANSFER`, etc.), Trigger Flag Reason, Date/Timestamp, and KYC Date of Birth.
- **Quick Preset Pills**: One-click fill buttons for rapid demonstration (₦12.5M threshold breach, PEP alert match, ₦2.4M compliant cash, corporate structuring).
- **Runtime Execution**:
  1. The custom transaction, account, and customer are dynamically committed into the local SQLite database (`data/regguard.db`).
  2. The LangGraph engine generates hypotheses and schedules dynamic tool calls (`threshold_calc`, `query_transactions`, `watchlist_lookup`, `regulation_search`).
  3. Programmatic critique checks and anti-hallucination guards inspect the evidence ledger.
  4. The synthesis engine automatically derives the proper legal disposition (`DRAFT_STR`, `CLEAR_NO_SUSPICION`, or `ESCALATE_TO_OFFICER`) and generates a complete audit memo.

---

## Environment Configuration & Live Model Integration

RegGuard AI resolves all model names, API keys, endpoints, and vector search models dynamically via environment variables (`.env`).

### `.env` Quick Configuration
```bash
cp .env.example .env
```

| Environment Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | Active LLM provider (`meta`, `ollama`, `mock`, `cached`) | `meta` |
| `REGGUARD_MODE` | State engine execution mode (`LIVE` or `CACHED`) | `LIVE` |
| `META_MODEL` | Meta model identifier | `muse-spark-1.3` |
| `META_BASE_URL` | Meta OpenAI-compatible endpoint | `https://api.meta.ai/v1` |
| `META_API_KEY` | Meta API authentication bearer key | `your_meta_api_key_here` |
| `LLM_MODEL` | Fallback general LLM model identifier | `llama-3.3-70b-instruct` |
| `OLLAMA_MODEL` / `OLLAMA_BASE_URL` | Local Ollama endpoint and model | `llama3.3:70b` (`http://localhost:11434/v1`) |
| `EMBEDDING_DENSE_MODEL` | FastEmbed dense model for Qdrant | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_SPARSE_MODEL` | FastEmbed sparse BM25 model for Qdrant | `Qdrant/bm25` |

> **Graceful Fallback**: If `META_API_KEY` is not provided or contains a placeholder, the engine automatically falls back to the deterministic offline `MockLLMProvider`, allowing test runs and offline demos to execute without crashing on network or credential errors. When a live key is present, all completions are routed live with automatic Markdown codeblock sanitization on JSON outputs.

---

## Empirical Benchmark & Ablation Evaluation

RegGuard is evaluated on 132 synthetic cases (`data/eval_dataset.json`, generated by `scripts/generate_eval_dataset.py`): a 120-case tuning split across six strata (structuring, PEP matches, temporal reconciliation, missing KYC, contradictory evidence, adversarial narration) plus a 12-case held-out split with distinct names, boundary amounts, dates, and paraphrased narrations. Held-out cases are never used to tune prompts or heuristics. Reproduce with:

```bash
python scripts/run_eval.py --mode full --split tuning  --provider mock --update-readme
python scripts/run_eval.py --mode full --split heldout --provider mock
python scripts/run_eval.py --mode full --split heldout --provider live   # real Muse Spark / configured provider
```

The mock-provider run measures the graph, tools, and deterministic guardrails — it does **not** measure LLM quality. Single-shot and model-vs-model comparisons are only reported from `--provider live` runs; no model comparison is claimed until both models are run through the same harness. Latest held-out result (mock provider): Full RegGuard 66.7% accuracy vs tuning-split 94.2% — the gap is reported deliberately; the 4 held-out errors are all over-escalations to a human officer (safe failure direction), with 0 unsafe clears.

### Evaluation results (auto-generated by `scripts/run_eval.py`)

> Provider: **mock-provider simulation (deterministic offline provider, no LLM network calls — measures the graph/tools/guardrails, not model quality)** | Split: `tuning` | Cases: 120 | Dataset hash: `ebb4b69e478792e8` | Git: `b9558a4` | Generated: 2026-11-03T04:56:05Z
> Labeling rationale: an exact corroborated PEP/sanctions match is labeled `DRAFT_STR` as shorthand for "reportable high-risk match requiring STR/EDD filing review"; an uncorroborated name-only or DOB-mismatched match is labeled `ESCALATE_TO_OFFICER`. This is a synthetic benchmark labeling convention, not a claim that PEP status alone is an STR offence.

| System | Accuracy (95% CI) | Macro-F1 | STR→CLEAR | ESC→CLEAR (unsafe) | CLEAR→STR | Escalation F1 | Clause Recall@2 | p50 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| (a) Single-shot LLM (no tools) | not run (requires `--provider live`) | — | — | — | — | — | — | — |
| (b) LLM + tools/RAG (no critique/refine) | 45.8% (37–55) | 44.8% | 2.9% | 15.6% | 0.0% | 0.0% | 46.7% | 24 ms |
| (c) Full RegGuard (critique/refine + guards) | 94.2% (88–97) | 94.1% | 0.0% | 3.1% | 0.0% | 94.7% | 46.7% | 40 ms |

Full RegGuard safety detail: unsupported-claim rate 0.0%, citation-resolved rate 76.8%, temporal-violation rate on pre-2022 cases 0.0% (n=10), expected-clause citation rate 55.0%, determinism over 10 repeats 1.0, majority-class baseline 53.3%. LLM usage during this run: {'calls': 0, 'schema_valid': 0, 'schema_total': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}. Per-case predictions are stored in the `eval_results_*.json` artifact. Model-vs-model claims require two `--provider live` runs with different configured models; no such comparison is asserted here.

---

## Runbook & Verification

### 1. Run Complete Pytest Suite (All 44 Tests Passing)
```bash
python3 -m pytest tests/ -v
```
✓ Validates AST security gates, local SQLite, fuzzy watchlist lookup, threshold math, hybrid Qdrant search, FastAPI SSE lifecycle, dynamic tool dispatch, critique & refine anti-hallucination loops, full multi-case end-to-end graph runs, Day 7 deterministic replay engine, Day 8 responsive frontend structure, Day 9 audit memo / cryptographic ledger exports, dynamic custom transaction submission, and dynamic environment configuration.

### 2. Launch Local FastAPI & Responsive Dashboard Server
```bash
python3 scripts/start_server.py
```
→ Open `http://localhost:8000` (or `http://127.0.0.1:8000`) in any browser.  
✓ Test interactive case execution, mode toggling (`LIVE` / `CACHED`), officer decision submissions, interactive block hash inspection with browser Web Crypto SHA-256 verification, and full-screen STR report viewing.

### 3. Run Dedicated Day 9 Audit Memo & Export Test Suite
```bash
python3 -m pytest tests/test_day9_export.py -v
```
✓ Asserts Markdown and HTML audit memo generation for Cases A, B, and C, deterministic canonical JSON hashing, and FastAPI export endpoints (`/audit_memo`, `/export/markdown`, `/export/html`, `/claims/{id}/verify`).

### 3. Run Dedicated Day 8 Responsive Frontend Test Suite
```bash
python3 -m pytest tests/test_day8_frontend.py -v
```
✓ Asserts responsive viewport tags, absence of fixed 1280x720 constraints, three-column DOM presence, and live SSE streaming lifecycle.

### 4. Run Multi-Case Demonstration CLI in CACHED Mode
```bash
python3 scripts/run_cases.py --mode CACHED --case all
```
✓ Executes Cases A, B, and C in offline CACHED mode using deterministic replay fixtures, displaying transition paths, tool calls, ledger appends, SHA-256 hash checks, and formatted synthesis previews.
