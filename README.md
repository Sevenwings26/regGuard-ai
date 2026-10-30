# RegGuard AI — Agentic AI Compliance Investigator
**Nigeria CBN AML/CFT Compliance Automation**

RegGuard AI is an autonomous compliance agent designed to investigate flagged financial transactions across regulatory rules, transaction histories, and sanctions/PEP watchlists without hallucinating conclusions.

---

## Architecture Core: Plan → Act → Critique → Refine → Synthesize

When evidence is ambiguous, contradictory, or insufficient, RegGuard AI reformulates queries or escalates to a human compliance officer. It **never** fabricates a conclusion.

### Routing Rule Invariant
> `escalate` is only reachable via `synthesize`; `synthesize` is always visited before terminal state (`concluded` or `escalated`).

---

## Tool & Data Layer (Day 2 Deliverables)

1. **AST-Guarded Read-Only SQLite (`tools/ast_guard.py`, `tools/sql_tool.py`)**:
   - `sqlglot` parses AST to enforce single `SELECT` statements and whitelist access to `["transactions", "customers", "accounts"]`.
   - Rejects `DROP`, `UPDATE`, `DELETE`, `INSERT`, `PRAGMA`, and semicolon chaining.
   - Connects to `data/regguard.db` with `?mode=ro`.
2. **Qdrant Local Hybrid RRF Retrieval (`tools/qdrant_hybrid.py`)**:
   - Dense embeddings (`BAAI/bge-small-en-v1.5`) + Sparse BM25 (`Qdrant/bm25`) with Reciprocal Rank Fusion.
   - Pre-indexed in `data/qdrant_storage/` (zero cloud dependencies, <150ms local startup).
   - Enforces temporal cutoffs (`effective_before <= tx_timestamp`) for historic regulatory matching.
3. **Watchlist Fuzzy Matcher (`tools/watchlist_tool.py`)**:
   - Matches against `data/seeded_watchlist.json` with DOB corroboration (`EXACT`, `MISMATCH`, `UNAVAILABLE`).
4. **CBN Threshold & Structuring Calculator (`tools/threshold_tool.py`)**:
   - Evaluates N5,000,000 (individual) and N10,000,000 (corporate) limits.
   - Automatically detects smurfing (2+ deposits under threshold aggregating to > limit within rolling 72 hours).

---

## Runbook & Verification

### 1. Run Day 2 Tool & Security Test Suite
```bash
python3 -m pytest tests/test_day2.py
```
✓ Verifies AST security gate, read-only SQLite execution, watchlist fuzzy search, threshold math, and Qdrant local hybrid RRF retrieval.

### 2. Verify Reducer Immutability
```bash
python3 scripts/check_reducers.py
```
✓ Asserts 3 sequential claims across fake nodes, zero overwrites, and intact hash chain.

### 3. Run Case B Mock Simulation
```bash
python3 scripts/run_mock.py
```
✓ Runs Case B non-linear state machine: `plan -> act -> critique -> refine -> act -> critique -> synthesize -> escalate`.
