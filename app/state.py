import hashlib
import json
import operator
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

# Status enums
ClaimStatus = Literal["supported", "insufficient", "contradicted", "superseded"]
FinalStatus = Literal["in_progress", "concluded", "escalated"]

class Claim(BaseModel):
    """
    Tamper-evident factual claim chained with SHA-256.
    """
    claim_id: str
    text: str
    supporting_sources: List[str] = Field(default_factory=list)
    status: ClaimStatus
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prev_hash: str
    hash: str

def compute_claim_hash(claim_data: Dict[str, Any], prev_hash: str) -> str:
    """
    Computes a deterministic SHA-256 hash over canonical JSON representation
    of the claim combined with prev_hash.
    """
    canonical_payload = {
        "claim_id": str(claim_data["claim_id"]),
        "text": str(claim_data["text"]).strip(),
        "supporting_sources": sorted([str(s).strip() for s in claim_data.get("supporting_sources", [])]),
        "status": str(claim_data["status"]),
        "timestamp": str(claim_data["timestamp"]),
        "prev_hash": str(prev_hash),
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

def create_claim(
    claim_id: str,
    text: str,
    supporting_sources: List[str],
    status: ClaimStatus,
    prev_hash: str,
    timestamp: Optional[str] = None
) -> Claim:
    """
    Factory to construct and hash a claim.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    claim_data = {
        "claim_id": claim_id,
        "text": text,
        "supporting_sources": supporting_sources,
        "status": status,
        "timestamp": ts,
        "prev_hash": prev_hash,
    }
    claim_hash = compute_claim_hash(claim_data, prev_hash)
    return Claim(
        claim_id=claim_id,
        text=text,
        supporting_sources=supporting_sources,
        status=status,
        timestamp=ts,
        prev_hash=prev_hash,
        hash=claim_hash,
    )

def verify_claims_chain(claims: List[Claim]) -> Tuple[bool, Optional[int]]:
    """
    Verifies that every claim in the list has a valid hash and correctly links
    to prev_hash. Returns (True, None) if intact, or (False, broken_index).
    """
    expected_prev = "0" * 64
    for idx, claim in enumerate(claims):
        claim_dict = claim.model_dump()
        if claim_dict["prev_hash"] != expected_prev:
            return False, idx
        computed = compute_claim_hash(claim_dict, expected_prev)
        if computed != claim_dict["hash"]:
            return False, idx
        expected_prev = claim_dict["hash"]
    return True, None

class CritiqueDecision(BaseModel):
    """Structured critique output consumed by routing and refine/act nodes."""
    sufficient: bool
    reason: str
    missing: List[str] = Field(default_factory=list)

from typing_extensions import TypedDict

class InvestigationState(TypedDict):
    """
    Core state for the RegGuard compliance agent workflow.
    Uses operator.add reducers for claims, unresolved_questions, and event_log
    to guarantee append-only immutability.
    """
    case_id: str
    jurisdiction: str
    flagged_transaction: Dict[str, Any]
    claims: Annotated[List[Claim], operator.add]
    unresolved_questions: Annotated[List[str], operator.add]
    retry_count: int
    max_retries: int
    current_node: str
    event_log: Annotated[List[Dict[str, Any]], operator.add]
    last_event_sequence: int  # Monotonically increasing sequence tracker for 1..N SSE events
    evidence_sufficient: bool
    final_status: FinalStatus
    critique_decision: Optional[Dict[str, Any]]
    audit_memo: Optional[Dict[str, Any]]
    planned_queries: List[Dict[str, Any]]  # Scheduled tool calls passed from plan or refine to act node.
    mode: Optional[str]  # Execution mode: "LIVE" or "CACHED"
