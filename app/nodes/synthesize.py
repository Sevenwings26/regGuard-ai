import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from app.state import InvestigationState, Claim
from app.events import EventType, create_event

FIXTURES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures"))

def load_case_fixture(case_id: str) -> Dict[str, Any]:
    """Helper to load corresponding fixture if available."""
    cid = case_id.lower()
    if "case-a" in cid or "case_a" in cid or "structuring" in cid:
        filename = "mock_case_a.json"
    elif "case-c" in cid or "case_c" in cid or "temporal" in cid:
        filename = "mock_case_c.json"
    else:
        filename = "mock_case_b.json"

    filepath = os.path.join(FIXTURES_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def synthesize_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Synthesizes findings into an audit package.
    Branches on evidence sufficiency:
      - concluded: full STR draft + memo (or clearance certificate if compliant)
      - escalated: dossier of unresolved questions, collected evidence, and verbatim critique missing list.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    evidence_sufficient = state.get("evidence_sufficient", False)
    critique_decision = state.get("critique_decision", {}) or {}
    tx = state.get("flagged_transaction", {}) or {}
    customer_name = tx.get("customer_name", "Subject")
    account_id = tx.get("account_id", "N/A")
    claims: List[Claim] = state.get("claims", [])
    
    claims_serialized = [
        claim.model_dump() if hasattr(claim, "model_dump") else claim
        for claim in claims
    ]
    tip_hash = claims[-1].hash if claims else ("0" * 64)

    fixture_data = load_case_fixture(case_id)
    synth_fixture = fixture_data.get("mock_responses", {}).get("synthesis", {})

    now = datetime.now(timezone.utc).isoformat()
    events = []

    if not evidence_sufficient:
        # Branch 1: final_status == escalated
        final_status = "escalated"
        verbatim_missing = critique_decision.get("missing", [])
        if not verbatim_missing:
            verbatim_missing = ["Unresolved risk factors and uncorroborated customer profile."]

        summary = synth_fixture.get(
            "summary",
            f"Investigation into customer {customer_name} ({account_id}) resulted in unresolved compliance "
            f"ambiguity. Watchlist and transaction evidence could not definitively substantiate or dismiss risk."
        )

        memo = {
            "disposition": "ESCALATE_TO_OFFICER",
            "case_id": case_id,
            "subject_name": customer_name,
            "account_id": account_id,
            "summary": summary,
            "why_could_not_conclude": verbatim_missing,
            "unresolved_questions": state.get("unresolved_questions", []),
            "evidence_collected": claims_serialized,
            "claims_count": len(claims),
            "ledger_tip_hash": tip_hash,
            "recommended_officer_action": "Conduct manual secondary KYC verification (biometrics / secondary ID document) and verify transaction source of funds.",
            "generated_at": now
        }

        events.append(create_event(
            event_type=EventType.SYNTHESIS_STARTED,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "status": "preparing_dossier",
                "message": "Critique marked evidence insufficient and retries exhausted. Preparing compliance dossier."
            },
            timestamp=now
        ))

        events.append(create_event(
            event_type=EventType.SYNTHESIS_COMPLETE,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "final_status": "escalated",
                "disposition": "ESCALATE_TO_OFFICER",
                "dossier": memo
            },
            timestamp=now
        ))

    else:
        # Branch 2: final_status == concluded
        final_status = "concluded"
        critique_reason = str(critique_decision.get("reason", "")).lower()
        is_cleared = (
            "does not breach" in critique_reason or
            "complied" in critique_reason or
            "no suspicion" in critique_reason or
            "clear" in critique_reason
        )

        if is_cleared:
            disposition = "CLEAR_NO_SUSPICION"
            status_desc = "clearing_flag"
            msg = "Evidence sufficient. Transaction compliant with applicable regulatory limit. Recommending clear flag."
            summary = synth_fixture.get(
                "summary",
                f"Investigation into transaction {tx.get('transaction_id')} concluded with no suspicion. "
                f"Initial flag resolved: governing regulation in force at transaction timestamp ({tx.get('timestamp')}) "
                f"was verified and transaction is fully compliant."
            )
            governing_limit = 10000000.0 if ("corp" in str(account_id).lower() or tx.get("dob") is None) else 5000000.0

            memo = {
                "disposition": disposition,
                "case_id": case_id,
                "subject_name": customer_name,
                "account_id": account_id,
                "summary": summary,
                "cleared_reason": critique_decision.get("reason", "Transaction complies with applicable regulatory thresholds."),
                "applicable_regulation": "CBN-AML-2013-SEC-02-1",
                "governing_limit": governing_limit,
                "transaction_amount": tx.get("amount", 0.0),
                "violations_found": [],
                "recommended_action": "Clear compliance flag. No filing required.",
                "claims_count": len(claims),
                "ledger_tip_hash": tip_hash,
                "evidence_collected": claims_serialized,
                "generated_at": now
            }
        else:
            disposition = "DRAFT_STR"
            status_desc = "preparing_str"
            msg = "Evidence sufficient. Structuring/AML breach substantiated. Drafting Suspicious Transaction Report."
            summary = synth_fixture.get(
                "summary",
                f"Investigation into customer {customer_name} ({account_id}) verified intentional "
                f"transaction structuring to evade statutory individual cash limits under CBN AML/CFT Regulations 2022."
            )
            violations = synth_fixture.get("violations_found") or [
                s for c in claims for s in c.supporting_sources if "CBN-AML-2022" in s
            ] or ["CBN-AML-2022-SEC-10-3"]
            violations = list(dict.fromkeys(violations))

            draft_str = {
                "reporting_entity": "RegGuard Demo Bank Nigeria",
                "investigation_id": case_id,
                "subject_name": customer_name,
                "account_id": account_id,
                "bvn": tx.get("bvn", "N/A"),
                "flag_reason": tx.get("flag_reason"),
                "narrative": (
                    f"Customer {customer_name} conducted multiple structured cash deposits aggregating "
                    f"in excess of the statutory individual threshold of N5,000,000 within a rolling 48-hour window. "
                    f"The transactions exhibit clear structuring/smurfing characteristics in violation of CBN AML/CFT 2022 Section 10(3)."
                ),
                "violations_found": violations,
                "statutory_violation": "CBN AML/CFT Regulations 2022 Section 10(3) (Prohibition of Structuring and Smurfing)",
                "filing_deadline": "Within 24 hours pursuant to CBN AML/CFT Regulations 2022",
                "merkle_root": tip_hash,
                "ledger_tip_hash": tip_hash
            }

            memo = {
                "disposition": disposition,
                "case_id": case_id,
                "subject_name": customer_name,
                "account_id": account_id,
                "summary": summary,
                "violations_found": violations,
                "draft_str": draft_str,
                "recommended_action": synth_fixture.get(
                    "recommended_action",
                    "File Suspicious Transaction Report (STR) with NFIU within 24 hours."
                ),
                "claims_count": len(claims),
                "ledger_tip_hash": tip_hash,
                "evidence_collected": claims_serialized,
                "generated_at": now
            }

        events.append(create_event(
            event_type=EventType.SYNTHESIS_STARTED,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "status": status_desc,
                "message": msg
            },
            timestamp=now
        ))

        events.append(create_event(
            event_type=EventType.SYNTHESIS_COMPLETE,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "final_status": "concluded",
                "disposition": disposition,
                "memo": memo
            },
            timestamp=now
        ))

    return {
        "current_node": "synthesize",
        "final_status": final_status,
        "audit_memo": memo,
        "last_event_sequence": seq + len(events),
        "event_log": events
    }

def escalate_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Terminal escalation handoff to human compliance officer.
    Receives dossier compiled by synthesize.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    now = datetime.now(timezone.utc).isoformat()
    memo = state.get("audit_memo", {}) or {}
    why_unresolved = memo.get("why_could_not_conclude", ["Unresolved risk factors"])

    event = create_event(
        event_type=EventType.ESCALATION,
        sequence_number=seq + 1,
        investigation_id=case_id,
        payload={
            "status": "ESCALATED_TO_HUMAN_OFFICER",
            "case_id": case_id,
            "why_could_not_conclude": why_unresolved,
            "unresolved_questions": state.get("unresolved_questions", []),
            "total_claims_in_ledger": len(state.get("claims", [])),
            "ledger_tip_hash": memo.get("ledger_tip_hash", "0" * 64)
        },
        timestamp=now
    )

    return {
        "current_node": "escalate",
        "final_status": "escalated",
        "last_event_sequence": seq + 1,
        "event_log": [event]
    }
