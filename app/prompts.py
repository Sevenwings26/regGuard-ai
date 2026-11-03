import json
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Structured LLM Output Schemas
# ---------------------------------------------------------------------------

class ToolCallSpec(BaseModel):
    tool_name: Literal["regulation_search", "query_transactions", "watchlist_lookup", "threshold_calc"]
    parameters: Dict[str, Any] = Field(default_factory=dict)

class InvestigationPlan(BaseModel):
    hypotheses: List[str] = Field(
        ...,
        description="3 testable compliance hypotheses (e.g. structuring, PEP exposure, lack of business rationale)"
    )
    initial_questions: List[str] = Field(
        ...,
        description="Concrete factual questions that need verification"
    )
    planned_tool_calls: List[ToolCallSpec] = Field(
        ...,
        description="Initial tool invocations to collect evidence"
    )

class CritiqueDecision(BaseModel):
    sufficient: bool = Field(
        ...,
        description="True if evidence conclusively answers hypotheses without gaps or contradictions"
    )
    assessment: Literal["SATISFIED", "INSUFFICIENT", "CONTRADICTED", "AMBIGUOUS"] = Field(
        default="INSUFFICIENT",
        description="Overall evidentiary assessment status"
    )
    recommended_disposition: Literal["DRAFT_STR", "CLEAR_NO_SUSPICION"] = Field(
        default="CLEAR_NO_SUSPICION",
        description="Structured disposition recommended when sufficient: DRAFT_STR if evidence substantiates a breach, CLEAR_NO_SUSPICION if verified compliant. Ignored when sufficient is False (case escalates)."
    )
    reason: str = Field(
        ...,
        description="Detailed rationale explaining the assessment"
    )
    missing: List[str] = Field(
        default_factory=list,
        description="List of specific missing evidence items or unresolved questions"
    )
    detected_contradictions: List[str] = Field(
        default_factory=list,
        description="List of factual or temporal contradictions detected"
    )
    suggested_queries: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Suggested tool calls to resolve gaps or contradictions"
    )

class RefinePlan(BaseModel):
    action: str = Field(
        ...,
        description="Actionable explanation of why queries are being reformulated and what gap is being targeted"
    )
    planned_tool_calls: List[ToolCallSpec] = Field(
        ...,
        description="Targeted queries addressing the specific critique gaps"
    )

class ClaimExtraction(BaseModel):
    text: str = Field(..., description="Factual assertion derived strictly from tool results")
    supporting_sources: List[str] = Field(..., description="IDs of source clauses, transactions, or watchlist entries")
    status: Literal["supported", "insufficient", "contradicted", "superseded"] = Field(..., description="Evidentiary status")

class ClaimsSynthesis(BaseModel):
    claims: List[ClaimExtraction] = Field(..., description="List of factual claims extracted from tool results")

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """You are RegGuard AI, an expert compliance investigator operating under Nigeria's Central Bank of Nigeria (CBN) AML/CFT Regulations 2022.

Your duty:
1. Decompose flagged transactions into rigorous, non-speculative investigation hypotheses.
2. Formulate factual questions covering statutory reporting thresholds (N5M individual / N10M corporate), PEP exposure, and transaction structuring (smurfing within 48-72h).
3. Schedule initial tool calls:
   - 'regulation_search': to retrieve relevant CBN regulatory clauses from Qdrant.
   - 'query_transactions': to execute read-only SQL queries over transaction history.
   - 'watchlist_lookup': to check PEP/sanctions records with DOB and alias checks.
   - 'threshold_calc': to evaluate mathematical turnover against limits.

Never guess or assume customer innocence or guilt. Focus entirely on verifiable evidence."""

def build_plan_prompt(flagged_tx: Dict[str, Any], jurisdiction: str = "NGA_CBN") -> str:
    return f"""Investigate the following flagged transaction:
Jurisdiction: {jurisdiction}
Transaction Metadata:
- Transaction ID: {flagged_tx.get('transaction_id')}
- Account ID: {flagged_tx.get('account_id')}
- Customer Name: {flagged_tx.get('customer_name')}
- DOB (KYC): {flagged_tx.get('dob')}
- Amount: {flagged_tx.get('amount'):,.2f} {flagged_tx.get('currency', 'NGN')}
- Timestamp: {flagged_tx.get('timestamp')}
- Flag Reason: {flagged_tx.get('flag_reason')}

Generate a comprehensive InvestigationPlan."""

CRITIQUE_SYSTEM_PROMPT = """You are RegGuard AI's anti-hallucination verification engine.
Your single most critical mandate: DOES THE EVIDENCE IN THE LEDGER STRICTLY SUPPORT THE HYPOTHESES?
If not, you MUST mark evidence as insufficient, ambiguous, or contradicted — DO NOT GUESS.

Apply three non-negotiable compliance verification checks:
1. TEMPORAL CONSISTENCY:
   Verify that transaction timestamp is on or after the effective date of any cited regulation clause.
   If a 2021 transaction cites a 2022 regulation, this is a FATAL TEMPORAL CONTRADICTION. Mark assessment="CONTRADICTED", sufficient=false.
2. ENTITY & DEMOGRAPHIC INTEGRITY:
   If a watchlist match is found with high name similarity, verify secondary attributes (DOB, nationality).
   If there is a significant DOB discrepancy (e.g. 1994 vs 1961), you CANNOT conclude innocence or guilt without secondary corroboration. Mark assessment="INSUFFICIENT" or "AMBIGUOUS", sufficient=false.
3. EVIDENTIARY COMPLETENESS:
   Every statutory conclusion (e.g. structuring) must be mathematically substantiated by concrete transaction rows and active regulation clauses.

If any check fails or is incomplete, set sufficient=false and specify the exact missing evidence in 'missing'."""

def build_critique_prompt(
    flagged_tx: Dict[str, Any],
    claims: List[Dict[str, Any]],
    unresolved_questions: List[str],
    retry_count: int,
    max_retries: int
) -> str:
    serialized_claims = json.dumps(claims, indent=2)
    return f"""Evaluate the current investigation evidence ledger for this case:
Flagged Transaction:
- ID: {flagged_tx.get('transaction_id')}
- Customer: {flagged_tx.get('customer_name')}
- KYC DOB: {flagged_tx.get('dob')}
- Amount: {flagged_tx.get('amount')} {flagged_tx.get('currency', 'NGN')}
- Timestamp: {flagged_tx.get('timestamp')}
- Flag: {flagged_tx.get('flag_reason')}

Current Iteration Retry: {retry_count} / Max Retries: {max_retries}
Current Unresolved Questions: {unresolved_questions}

Evidence Claims Ledger:
{serialized_claims}

Provide a rigorous CritiqueDecision."""

REFINE_SYSTEM_PROMPT = """You are RegGuard AI's query refinement engine.
Your duty: Ingest critique evidence gaps and detected contradictions, and formulate targeted, corrective tool queries to resolve them.
- If temporal contradiction: add strict 'effective_before' date filter matching transaction timestamp.
- If watchlist DOB ambiguity: query customer secondary identifiers (BVN, nationality) or transaction history.
Never repeat the exact same failed query without adding corrective parameters."""

def build_refine_prompt(
    critique_decision: Dict[str, Any],
    flagged_tx: Dict[str, Any],
    retry_count: int
) -> str:
    return f"""Reformulate investigation queries based on critique evaluation:
Transaction: {flagged_tx.get('transaction_id')} (Date: {flagged_tx.get('timestamp')})
Critique Assessment: {critique_decision.get('assessment')}
Critique Reason: {critique_decision.get('reason')}
Evidence Gaps: {critique_decision.get('missing')}
Contradictions: {critique_decision.get('detected_contradictions')}
Retry Count: {retry_count}

Produce an actionable RefinePlan with specific planned_tool_calls."""
