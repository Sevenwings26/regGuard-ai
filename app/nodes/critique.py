import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.state import InvestigationState, Claim
from app.events import EventType, create_event
from app.prompts import (
    CritiqueDecision,
    CRITIQUE_SYSTEM_PROMPT,
    build_critique_prompt
)
from core.llm_adapter import get_llm_provider

def evaluate_temporal_consistency(
    tx_timestamp: str,
    claims: List[Claim],
    superseded_ids: Optional[Any] = None
) -> List[Dict[str, str]]:
    """
    Checks if any active cited regulation clause was enacted AFTER the transaction timestamp.
    Returns list of detected contradictions.
    Does NOT mutate claims in-place to preserve tamper-evident hash chaining.
    """
    contradictions = []
    if not tx_timestamp:
        return contradictions

    clean_tx_date = tx_timestamp[:10]  # YYYY-MM-DD
    superseded = set(superseded_ids) if superseded_ids else set()

    # If a valid pre-dating governing regulation (e.g. 2013) has been retrieved into the ledger,
    # then any 2022 clause is superseded by it.
    has_valid_governing_reg = any(
        ("2013" in c.text or "CBN-AML-2013" in " ".join(c.supporting_sources))
        for c in claims
    )
    if has_valid_governing_reg and clean_tx_date < "2022-11-01":
        for c in claims:
            if "CBN-AML-2022" in " ".join(c.supporting_sources) or "2022" in c.text:
                superseded.add(c.claim_id)

    for claim in claims:
        # Ignore claims that have already been marked contradicted or superseded
        if claim.claim_id in superseded or claim.status in ("contradicted", "superseded"):
            continue

        text = claim.text
        sources = " ".join(claim.supporting_sources)
        
        if ("CBN-AML-2022" in sources or "2022" in text) and clean_tx_date < "2022-11-01":
            contradictions.append({
                "claim_id": claim.claim_id,
                "reason": f"Transaction timestamp ({clean_tx_date}) predates effective date (2022-11-01) of cited 2022 regulation."
            })
    return contradictions

def evaluate_demographic_consistency(claims: List[Claim]) -> bool:
    """
    Returns True if any claim reflects an unresolved DOB/demographic conflict.
    """
    for claim in claims:
        text_lower = claim.text.lower()
        if "conflict" in text_lower or "discrepancy" in text_lower or "mismatch" in text_lower:
            if "dob" in text_lower or "demographic" in text_lower:
                return True
        if claim.status == "insufficient":
            return True
    return False

def critique_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Evaluates evidence in the ledger against hypotheses and compliance invariants.
    Detects contradictions, demographic mismatches, and evidentiary gaps.
    Returns a structured CritiqueDecision:
    { "sufficient": bool, "assessment": str, "reason": str, "missing": [str] }
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)
    tx = state.get("flagged_transaction", {})
    claims = state.get("claims", [])
    now = datetime.now(timezone.utc).isoformat()

    # Track claims already superseded in previous passes to prevent re-flagging loops
    superseded_ids = {
        e["payload"]["superseded_claim_id"]
        for e in state.get("event_log", [])
        if e.get("event_type") == EventType.CLAIM_SUPERSEDED and "superseded_claim_id" in e.get("payload", {})
    }

    # 1. Programmatic Invariant Guard 1: Temporal Check
    temporal_contradictions = evaluate_temporal_consistency(
        tx.get("timestamp", ""),
        claims,
        superseded_ids=superseded_ids
    )

    # 2. Programmatic Invariant Guard 2: Demographic / DOB Check
    has_demographic_mismatch = evaluate_demographic_consistency(claims)

    # 3. LLM Provider Evaluation
    llm = get_llm_provider(mode=state.get("mode"))
    claims_payload = [
        {
            "claim_id": c.claim_id,
            "text": c.text,
            "status": c.status,
            "supporting_sources": c.supporting_sources
        }
        for c in claims
    ]
    prompt = build_critique_prompt(
        flagged_tx=tx,
        claims=claims_payload,
        unresolved_questions=state.get("unresolved_questions", []),
        retry_count=retry_count,
        max_retries=max_retries
    )

    try:
        critique_decision: CritiqueDecision = llm.complete_structured(
            schema=CritiqueDecision,
            prompt=prompt,
            system=CRITIQUE_SYSTEM_PROMPT
        )
    except Exception as llm_err:
        critique_decision = CritiqueDecision(
            sufficient=False,
            assessment="INSUFFICIENT",
            reason=f"Evidentiary reasoning could not be validated against compliance schema: {llm_err}",
            missing=[f"Model reasoning failed schema validation: {llm_err}"]
        )

    # 4. Enforce Hard Evidentiary Compliance Guardrails
    # If temporal contradiction exists but LLM missed it, guardrail overrides
    if temporal_contradictions and critique_decision.sufficient:
        critique_decision.sufficient = False
        critique_decision.assessment = "CONTRADICTED"
        critique_decision.detected_contradictions.extend([tc["reason"] for tc in temporal_contradictions])
        critique_decision.missing.append(f"Applicable regulation in force prior to {tx.get('timestamp')[:10]}")

    # If demographic mismatch is active without secondary resolution, cannot be sufficient
    if has_demographic_mismatch and critique_decision.sufficient:
        critique_decision.sufficient = False
        critique_decision.assessment = "AMBIGUOUS"
        if not critique_decision.missing:
            critique_decision.missing.append("Secondary biometric KYC or historical transaction pattern")

    decision_dict = critique_decision.model_dump()
    events = []
    new_unresolved = []

    # Emit appropriate SSE events
    if temporal_contradictions:
        for tc in temporal_contradictions:
            seq += 1
            events.append(create_event(
                event_type=EventType.CLAIM_SUPERSEDED,
                sequence_number=seq,
                investigation_id=case_id,
                payload={
                    "superseded_claim_id": tc["claim_id"],
                    "reason": tc["reason"]
                },
                timestamp=now
            ))

    if not critique_decision.sufficient:
        seq += 1
        events.append(create_event(
            event_type=EventType.EVIDENCE_INSUFFICIENT,
            sequence_number=seq,
            investigation_id=case_id,
            payload={
                "assessment": critique_decision.assessment,
                "reason": critique_decision.reason,
                "missing": critique_decision.missing,
                "detected_contradictions": critique_decision.detected_contradictions,
                "retry_count": retry_count,
                "max_retries": max_retries
            },
            timestamp=now
        ))

        # Log newly identified unresolved questions
        if critique_decision.missing:
            seq += 1
            events.append(create_event(
                event_type=EventType.UNRESOLVED_ADDED,
                sequence_number=seq,
                investigation_id=case_id,
                payload={
                    "unresolved_questions": critique_decision.missing,
                    "identified_by": "critique",
                    "iteration": retry_count + 1
                },
                timestamp=now
            ))
            new_unresolved = critique_decision.missing
    else:
        seq += 1
        events.append(create_event(
            event_type=EventType.STATE_TRANSITION,
            sequence_number=seq,
            investigation_id=case_id,
            payload={
                "from_node": "critique",
                "to_node": "synthesize",
                "decision": "SATISFIED",
                "reason": critique_decision.reason
            },
            timestamp=now
        ))

    return {
        "current_node": "critique",
        "evidence_sufficient": critique_decision.sufficient,
        "critique_decision": decision_dict,
        "unresolved_questions": new_unresolved,
        "last_event_sequence": seq,
        "event_log": events
    }
