# System Architecture & Component Topology

## Overview

RegGuard AI is an autonomous compliance investigation copilot designed for anti-money laundering (AML) and counter-financing of terrorism (CFT) analysts at regulated financial institutions operating under Central Bank of Nigeria (CBN) and Nigerian Financial Intelligence Unit (NFIU) mandates. The system ingests flagged high-risk transactions, coordinates an agentic state machine to query core banking records, searches regulatory law libraries, and matches watchlist databases, verifying all evidence through an adversarial critique loop before producing either a formal Suspicious Transaction Report (STR) draft, a statutory clearance certificate, or an escalation dossier for a human compliance officer.

---

## Runtime Workflow

A **state machine** is an execution model that transitions between defined nodes according to explicit routing logic. The core execution flow begins when an investigation request is received and progresses through deterministic steps:

```
[ User / Ingestion Trigger ]
            │
            ▼
        [ Plan ]
            │
            ▼
         [ Act ] ◄────────────────────────┐
            │                             │
            ▼                             │
       [ Critique ]                       │
       /          \                       │
[ Insufficient ]  [ Sufficient / Max Retries ]
     │                    │
     ▼                    ▼
 [ Refine ] ──────────────┘
                          │
                          ▼
                    [ Synthesize ]
                     /          \
            [ Escalated ]    [ Concluded ]
                 │                  │
                 ▼                  ▼
            [ Escalate ]         [ END ]
                 │             (DRAFT_STR /
                 ▼           CLEAR_NO_SUSPICION)
               [ END ]
```

Every state change emits a telemetry packet streamed to the client via **Server-Sent Events (SSE)**—an HTTP standard enabling servers to push real-time event updates to web browsers over a single persistent connection.

---

## Component Topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application & SSE                       │
│    (REST Endpoints: /investigations, /decision, /audit_memo, /stream)  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      LangGraph StateGraph Engine                       │
│      [plan] ──► [act] ──► [critique] ──► [refine] ──► [synthesize]     │
└─────────┬───────────────────────┬───────────────────────────────┬──────┘
          │                       │                               │
          ▼                       ▼                               ▼
┌──────────────────┐    ┌──────────────────┐    ┌────────────────────────┐
│ Regulation Search│    │Query Transactions│    │    Watchlist Lookup    │
│  (Qdrant Hybrid) │    │  (SQLite Core)   │    │  (SQLite + Fuzzy Jaro) │
└─────────┬────────┘    └─────────┬────────┘    └───────────┬────────────┘
          │                       │                         │
          ▼                       ▼                         ▼
┌──────────────────┐    ┌────────────────────────────────────────────────┐
│  Qdrant Storage  │    │            SQLite Database Engine              │
│ (Dense bge-small │    │  `data/bank_records.db` (transactions, core    │
│  + Sparse bm25)  │    │  accounts, customers, PEP & sanctions lists)   │
└──────────────────┘    └────────────────────────────────────────────────┘
```

The system coordinates several specialized subsystems:
1. **LangGraph Orchestrator (`app/graph.py`)**: Manages the directed graph of investigation nodes, enforces immutable transitions, and executes routing guards.
2. **Investigation Manager (`app/manager.py`)**: Maintains in-memory session lifecycles, runs async worker loops, and broadcasts events over SSE subscriber queues.
3. **Retrieval & Tooling Layer (`core/tools/`)**:
   - `regulation_search`: Queries regulatory statutes indexed in Qdrant using **Reciprocal Rank Fusion (RRF)**—an algorithm that combines dense semantic search and sparse keyword search rankings without requiring score normalization.
   - `query_transactions`: Executes parameterized SQL queries against banking ledger tables in SQLite (`data/bank_records.db`).
   - `watchlist_lookup`: Performs fuzzy name matching (Jaro-Winkler and Levenshtein) against PEP and sanctions databases.
4. **Cryptographic Proof Engine (`app/state.py`)**: Constructs a tamper-evident **hash chain**—a sequential series of records where each block contains the SHA-256 fingerprint of its predecessor. See [.docs/03-evidence-ledger-and-guardrails.md](03-evidence-ledger-and-guardrails.md) for verification mechanics.

---

## Routing Rule Table

The routing rules governing transitions out of `critique` and `synthesize` are copied verbatim from [app/graph.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/app/graph.py#L10-L31):

### Critique Node Routing (`route_critique`)

```python
if not sufficient and retry_count < max_retries:
    return "refine"

return "synthesize"
```

### Synthesis Node Routing (`route_synthesis`)

```python
if state.get("final_status") == "escalated":
    return "escalate"
return END
```

| Source Node | Condition Evaluated | Destination Node | Purpose |
| :--- | :--- | :--- | :--- |
| `critique` | `not sufficient and retry_count < max_retries` | `refine` | Evidence missing; request targeted follow-up queries. |
| `critique` | `sufficient` OR `retry_count >= max_retries` | `synthesize` | Evidence conclusive or retry budget exhausted. |
| `synthesize` | `final_status == "escalated"` | `escalate` | Package unresolved questions into human officer dossier. |
| `synthesize` | `final_status == "concluded"` | `END` | Publish final STR draft or clearance certificate. |

Notice that `escalate` cannot be reached directly from `critique`. Synthesis must always execute first to compile the evidence chain into an official audit memo.

---

## Why the Agent Loop Earns Its Complexity (Ablation Analysis)

A frequent question from technical evaluators is: *Why not run a single-shot prompt with function calling?*

The multi-node agent loop is essential due to the adversarial nature of financial compliance:

| Architectural Component | What Breaks if Ablated (Removed) | Empirical Failure Observed |
| :--- | :--- | :--- |
| **Plan Node** | Without structured hypothesis decomposition, tool dispatches are uncoordinated and unfocused. | Misses historical 48-hour transaction windows; overlooks temporal enactment boundaries. |
| **Act Node (Isolated Tools)** | Without deterministic SQL and vector retrieval, the model invents balances and clauses. | Pure hallucination of transaction amounts and non-existent circular sections. |
| **Critique Node (Adversarial Gate)** | **Single-Shot Prompting Failure**: In a single prompt, LLMs exhibit severe confirmation bias—assuming guilt on a 0.87 PEP name match. | Catastrophic false conviction in Case B (ignores 33-year KYC DOB mismatch) and Case C (applies 2022 law to 2021 transaction). |
| **Refine Node** | Without targeted query reformulation, any missing data causes premature termination. | Unnecessary escalations on trivial data gaps (e.g., failing to query secondary KYC DOB). |
| **Synthesize Node** | Without dedicated document compilation, outputs are unstructured chat text. | Unusable by regulatory examiners; lacks formal NFIU filing schedules and tamper-evident hashes. |

### Why `max_retries = 1`?

In high-stakes banking compliance, an autonomous agent must never spin in unbounded loops:
1. **Deterministic Latency & SLA**: Compliance teams operate under strict filing deadlines (e.g., CBN 24-hour STR mandate). An agent must have a deterministic execution bound (at most 2 tool passes).
2. **Pragmatic Escalation Policy**: If an initial hypothesis hits ambiguity (e.g., PEP name match) and a targeted secondary inquiry (KYC DOB cross-check) reveals a 33-year discrepancy, no further database querying can resolve the demographic doubt. Statutory AML regulations mandate that remaining ambiguity **must** be escalated to human officers.

---

## What This System Deliberately Does NOT Do

To maintain compliance integrity and operational safety, RegGuard AI explicitly excludes the following functionalities:

1. **No Autonomous Regulatory Filing**: The system will never transmit an STR directly to the NFIU goAML portal or external enforcement agencies. The agent drafts regulatory documents for formal human officer determination only.
2. **No Multi-Tenant Isolation**: The system runs as a single-institution compliance workbench with a local database and embedded vector store. It does not partition data across isolated bank tenants.
3. **No Heavy Cross-Encoder Reranker**: Hybrid retrieval in Qdrant relies strictly on native dense (`BAAI/bge-small-en-v1.5`) and sparse (`Qdrant/bm25`) reciprocal rank fusion. A secondary cross-encoder neural reranker is omitted to preserve low latency and run on commodity compute.
4. **No Dynamic Jurisdiction Engine**: Regulatory logic, reporting thresholds (e.g., ₦5,000,000 individual, ₦10,000,000 corporate), and statutory references are scoped specifically to Nigeria (CBN AML/CFT Regulations 2022 and 2013). Cross-border multi-jurisdiction rule engines are outside current scope.
