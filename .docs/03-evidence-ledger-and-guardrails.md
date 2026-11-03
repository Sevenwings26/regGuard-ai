# Evidence Ledger, Anti-Hallucination Guardrails & Audit Defense

## The Cryptographic Evidence Ledger

In regulatory anti-money laundering compliance, evidentiary defensibility is non-negotiable. External bank examiners and law enforcement regulators require mathematical certainty that investigative findings were not altered, deleted, or fabricated after the fact.

RegGuard AI implements an append-only, tamper-evident cryptographic ledger where every factual finding is recorded as a `Claim` block. Each block computes a SHA-256 hash across its canonical JSON representation and cryptographically embeds the hash of the preceding claim (`prev_hash`).

### Ledger Immutability Principles
1. **Append-Only Reducers**: The LangGraph state schema enforces list concatenation via `operator.add`. Nodes cannot delete, overwrite, or mutate previously committed claims.
2. **Mandatory Source Attribution**: Every claim requires at least one primary source entry in `supporting_sources` (e.g., `sqlite:transactions`, `watchlist:pep_database`, `qdrant:cbn_aml_2022`). Unsourced claims are rejected during critique.
3. **Independent Client-Side Verification**: Web clients can independently verify the hash chain using the browser's native Web Crypto API (`crypto.subtle.digest('SHA-256')`), comparing calculated digests against committed block hashes without trusting the backend server.

---

## Claim Status Lifecycle

Every claim in the ledger is assigned a status from the `ClaimStatus` enumeration defined in [app/state.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/app/state.py#L9):

```
       [ supported ] ─────────────► [ superseded ]
             ▲                            ▲
             │                            │
      [ insufficient ] ───────────────────┘
             ▲
             │
      [ contradicted ]
```

| Status | Definition | Triggering Condition |
| :--- | :--- | :--- |
| `supported` | Factual proposition corroborated by retrieved records. | Core banking query confirms cash aggregation exceeding ₦5,000,000 threshold. |
| `insufficient` | Evidence retrieved is incomplete, ambiguous, or lacks corroboration. | Watchlist search returns name match with 0.87 similarity, but secondary KYC attributes (DOB, nationality) are absent. |
| `contradicted` | Evidence directly refutes the initial suspicion or hypothesis. | KYC crosscheck reveals a 33-year date-of-birth discrepancy between customer and PEP profile. |
| `superseded` | Prior claim has been updated or clarified by higher-fidelity subsequent findings. | Preliminary name-only match is formally superseded by a definitive secondary attribute mismatch. |

---

## The Critique Node: Adversarial Evidence Guardrail

Large language models are inherently prone to premature closure and confirmation bias—assuming guilt or innocence based on surface-level keyword similarity. The `critique` node acts as an adversarial compliance auditor that strictly separates evidence verification from synthesis.

### The Structured Verdict Contract

Defined in [app/state.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/app/state.py#L87-L91), the critique node must produce a Pydantic-validated verdict:

```python
class CritiqueDecision(BaseModel):
    sufficient: bool
    reason: str
    missing: List[str] = Field(default_factory=list)
```

The critique engine does not invoke tools or generate narrative text. It rigorously evaluates the evidence ledger against three statutory tests:
1. **Source Corroboration**: Does every proposition link to an authentic database row or indexed regulation section?
2. **Temporal Alignment**: Is the transaction evaluated against the specific regulatory threshold in force at the transaction timestamp (e.g., 2013 corporate rules vs. 2022 individual limits)?
3. **Demographic Concordance**: For watchlist alerts, do secondary identity attributes (date-of-birth, BVN, nationality) align?

If any test fails, the node emits `sufficient = False` and populates `missing` with explicit data requirements. This contract prevents the downstream synthesis node from fabricating a conclusive disposition on speculative grounds.

---

## Routing Guard: Why Escalate Routes via Synthesize

In [app/graph.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/app/graph.py#L52-L72), the conditional routing enforces a strict topological invariant:

```
[ critique ] ──► [ synthesize ] ──► [ escalate ] ──► [ END ]
```

The system strictly disallows routing directly from `critique` to `escalate`. 

### Architectural Justification
If an investigation could abort directly from critique to escalation, the resulting handoff to the compliance officer would be an unformatted error state. By routing through `synthesize` first:
- The evidence ledger is sealed, calculating the final `ledger_tip_hash`.
- The verbatim critique list of unresolved questions (`why_could_not_conclude`) is bound into a formal officer escalation dossier.
- An official CBN audit memorandum is generated in both Markdown and HTML formats.
- The human officer receives a standardized compliance docket with specific recommended actions rather than raw debug logs.

---

## Known Limitations and Open Questions

To maintain honest engineering standards, the following architectural limitations are documented:

1. **Single-Institution Data Boundary**: The system operates within the core database of a single institution. Cross-bank smurfing networks that disperse transactions across multiple separate commercial banks cannot be tracked without NFIU central reporting feeds.
2. **Fixed Retries Budget**: The refinement loop is constrained by `max_retries = 1`. If secondary queries fail to resolve evidentiary ambiguity, the workflow halts and escalates rather than dynamically attempting exploratory search patterns.
3. **Small Model Schema Compliance**: Local quantized 8B-parameter models occasionally output structural wrappers or echo JSON schema `$defs` under complex prompts. The system employs defensive fallback normalization in [core/llm_adapter.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/core/llm_adapter.py#L495-L509) to ensure pipeline continuity.
4. **Volatile Session Memory**: Active SSE client sessions and real-time streaming buffers are managed in process memory by [app/manager.py](file:///home/techyz-admin/sevenwings/26-30-10-RegGuardAI/app/manager.py). If the backend daemon terminates unexpectedly, in-flight streams must be re-queried via REST snapshot endpoints.
