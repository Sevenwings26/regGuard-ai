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
```

Verify that `data/bank_records.db` and the embedded Qdrant vector storage directory (`data/qdrant_storage/`) exist.

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
