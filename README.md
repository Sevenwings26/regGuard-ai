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

## Runbook & Verification

### 1. Run Complete Pytest Suite (All 33 Tests Passing)
```bash
python3 -m pytest tests/ -v
```
✓ Validates AST security gates, local SQLite, fuzzy watchlist lookup, threshold math, hybrid Qdrant search, FastAPI SSE lifecycle, dynamic tool dispatch, critique & refine anti-hallucination loops, full multi-case end-to-end graph runs, Day 7 deterministic replay engine, Day 8 responsive frontend structure, and Day 9 audit memo / cryptographic ledger exports.

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
