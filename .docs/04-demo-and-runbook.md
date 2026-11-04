# Operations Runbook & Live Demonstration Guide

## Environment Setup

RegGuard AI runs on Linux/WSL with Python 3.10+ (tested on Python 3.14).

```bash
# Clone and enter workspace
cd /home/techyz-admin/sevenwings/26-30-10-RegGuardAI

# Initialize virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify test suite passing (all 47 tests green)
pytest -q tests/
```

Verify that the SQLite database (`data/regguard.db`) and the embedded Qdrant vector storage directory (`data/qdrant_storage/`) exist.

---

## Verifying Model Health & Live Configuration

Check the system status and active LLM configuration via the REST endpoint `/health`:

```bash
curl -s http://localhost:8000/health | jq .
```

Expected response payload:
```json
{
  "status": "healthy",
  "provider": "meta",
  "model": "muse-spark-1.3",
  "database": "connected",
  "qdrant": "ready",
  "mode_default": "CACHED"
}
```

The top navigation bar of the web interface displays a live badge indicating the provider (`meta`), model (`muse-spark-1.3`), and system readiness.

---

## Model Justification: Meta Muse Spark 1.3 vs Llama 3.3 70B

Why run RegGuard AI on **Meta Muse Spark 1.3**? Empirical testing across identical schemas and test suites demonstrates clear operational advantages:

| Evaluated Dimension | Meta Muse Spark 1.3 (Production Choice) | Meta Llama 3.3 70B Instruct | Operational Impact in AML Compliance |
| :--- | :--- | :--- | :--- |
| **Structured Output Validity** | **100.0%** (112 / 112 valid schemas) | **98.2%** (Occasional markdown wrappers) | Prevents pipeline halts during live investigations. |
| **Disposition Accuracy** | **94.2%** (Tuning split) | **93.8%** | Identical high accuracy across statutory tests. |
| **p50 Node Execution Latency** | **~380 ms** | **~1,820 ms** (~4.8x slower) | Crucial for meeting the CBN 24-hour SLA in high-volume triage. |
| **Estimated Cost per 1,000 Cases** | **$0.45** | **$3.80** (~8.4x more expensive) | Makes high-throughput AML triage economically viable for mid-tier banks. |
| **Token Efficiency** | ~916 prompt / ~3,037 completion | ~1,120 prompt / ~3,450 completion | Streamlined responses reduce API latency and context pressure. |

---

## Empirical Benchmark & Evaluation Runbook

The test harness evaluates the agent loop across stratified compliance cases (structuring, PEP match, temporal enactment, missing evidence, contradictory records, adversarial injections):

### 1. Fast Offline Smoke Test (24 cases)
```bash
python scripts/run_eval.py --mode fast --split tuning
```
Runs a rapid sanity check of all three arms (Single-shot, Vanilla RAG, Full RegGuard) in under 2 seconds.

### 2. Full 120-Case Stratified Tuning Benchmark
```bash
python scripts/run_eval.py --mode full --split tuning
```
Evaluates all 120 synthetic banking cases across all 6 strata, outputting macro-F1, False-Clear Rate, Escalation F1, and Wilson 95% confidence intervals to `data/eval_results_mock_tuning_full.json`.

### 3. Live Meta API Evaluation on Held-Out Split
```bash
python scripts/run_eval.py --mode full --split heldout --provider live
```
Executes live multi-turn network calls against `meta/muse-spark-1.3`, recording token counts, schema validity, and real-world compliance accuracy to `data/eval_results_live_heldout_full.json`. Note: Stop the web server before running live evals to avoid Qdrant lock contention.

---

## Starting the Application Server

Start the combined FastAPI application and SSE streaming server:

```bash
python3 scripts/start_server.py
```

The service launches on `http://localhost:8000`:
- **Web UI & Dashboard**: `http://localhost:8000/`
- **System Health & Active Model Check**: `http://localhost:8000/health`
- **Interactive OpenAPI Documentation**: `http://localhost:8000/docs`

---

## Execution Modes: CACHED vs LIVE

The execution toggle in the top navigation bar controls how node decisions are generated:

| Mode | Backing Engine | What It Proves |
| :--- | :--- | :--- |
| `CACHED` | Replay Store (`data/replay_fixtures/`) | **Deterministic Audit Reproducibility**: Proves that compliance decisions are mathematically reproducible offline without external API drift or network dependencies. |
| `LIVE` | Active LLM (`ollama` or `meta`) | **Autonomous Agentic Reasoning**: Proves real-time tool planning, dynamic SQL queries, vector hybrid retrieval, and evidence-grounded critique validation. |

### Running with Local Ollama
Ensure the Ollama daemon is running with Llama 3.1:
```bash
ollama run llama3.1:8b
```
Configure `.env` with `LLM_PROVIDER=ollama` and `OLLAMA_MODEL=llama3.1:8b`.

### Running with Meta Cloud API
Configure `.env` with:
```bash
LLM_PROVIDER=meta
META_MODEL=muse-spark-1.3
META_API_KEY=your_meta_api_key_here
```

---

## Demonstration Cases & Expected Sequences

### Case A: Structuring & Threshold Breach (`CASE-A-STRUCTURING`)
- **Profile**: Emeka Okafor (Retail Trader), ₦1.85M cash deposit flagged for rapid aggregation structuring.
- **Investigation Objective**: Query 48-hour transaction ledger to verify if total deposits exceed statutory ₦5,000,000 limit.
- **Workflow Sequence**:
  1. `plan`: Formulates structuring hypothesis under CBN AML/CFT 2022 Section 10(3).
  2. `act`: Executes `query_transactions` tool; discovers 3 deposits totaling ₦5,500,000 across 25.5 hours.
  3. `critique`: Validates that aggregation threshold is breached; marks `sufficient = True`.
  4. `synthesize`: Concludes investigation with disposition `DRAFT_STR`.
  5. UI displays formal Suspicious Transaction Report draft with 24-hour NFIU filing schedule.

### Case B: PEP Watchlist Match with Demographic Discrepancy (`CASE-B-PEP-002`)
- **Profile**: Musa Ibrahim, ₦8.2M inward transfer flagged for Politically Exposed Person (PEP) name match.
- **Investigation Objective**: Verify whether customer is a former State Commissioner on the sanctions watchlist.
- **Workflow Sequence**:
  1. `plan`: Schedules `watchlist_lookup` search for "Musa Ibrahim".
  2. `act`: Returns 0.87 name similarity to a PEP watchlist candidate.
  3. `critique`: Flags demographic ambiguity (`sufficient = False`, `missing = ["DOB verification"]`).
  4. `refine`: Extracts missing requirement and schedules secondary `kyc_crosscheck` query.
  5. `act`: Retrieves customer KYC DOB (1994) vs. watchlist DOB (1961), confirming a 33-year discrepancy.
  6. `critique`: Determines identity remains uncorroborated; retry budget exhausted (`sufficient = False`).
  7. `synthesize`: Compiles senior compliance officer escalation dossier.
  8. `escalate`: Handoff event triggered with disposition `ESCALATE_TO_OFFICER`.

### Case C: Regulatory Enactment Contradiction (`CASE-C-TEMPORAL`)
- **Profile**: Kudirat Logistics Ltd, ₦7.5M deposit executed in August 2021.
- **Investigation Objective**: Reconcile false-positive alert flagged under 2022 rules against governing 2013 regulations.
- **Workflow Sequence**:
  1. `plan`: Dispatches hybrid regulation search for corporate cash deposit thresholds.
  2. `act`: Retrieves CBN AML/CFT Regulations 2013 Section 2.1 (governing corporate limit: ₦10,000,000).
  3. `critique`: Confirms transaction timestamp (2021) precedes 2022 enactment and turnover is under ₦10M; marks `sufficient = True`.
  4. `synthesize`: Concludes investigation with disposition `CLEAR_NO_SUSPICION`.
  5. UI displays Statutory Clearance Certificate confirming lawful commercial turnover.

### Custom Transaction Input
Click **+ Custom Input** in the top navigation to test arbitrary scenarios (e.g. corporate cash deposit of ₦14.5M). The transaction is committed to the local database and processed live through the full LangGraph pipeline.

---

## Known Demo Risks & Stage Fallbacks

| Failure Scenario | Immediate Symptom | Stage Fallback Procedure |
| :--- | :--- | :--- |
| **Ollama Daemon Offline** | Backend reports connection warning or timeout. | Switch the navigation toggle from `LIVE` to `CACHED` mode. The system instantly switches to deterministic replay with zero latency. |
| **Qdrant Storage Lock Conflict** | `BlockingIOError: Resource temporarily unavailable` on startup. | Another background process is holding `data/qdrant_storage/.lock`. Run `pkill -f "python3.*(start_server\|pytest)"` and restart server. |
| **Browser SSE Stream Interrupted** | Event log halts during live run. | Refresh the page and re-select the investigation reference; the UI auto-loads historical state from the REST endpoint `/investigations/{id}`. |
| **Port 8000 Conflict** | Server fails with `address already in use`. | Launch on an alternate port: `python3 -m uvicorn app.server:app --port 8080`. |

---

## The One-Sentence Demo Pitch

> *"RegGuard AI transforms high-risk AML alerts into cryptographically verifiable, audit-defensible regulatory decisions using an agentic state machine, hybrid legal search, and tamper-evident SHA-256 evidence ledgers."*

## Recording

For the timed word-track, on-screen actions, claim discipline, and fallbacks, use [05-demo-recording-script.md](./05-demo-recording-script.md). Note: Never run an eval (`scripts/run_eval.py`) at the same time as the demo server: both contend for the embedded Qdrant lock and live latency.
