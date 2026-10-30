import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_case_b.json")

def synthesize_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Synthesizes findings into an audit package.
    Branches on evidence sufficiency:
      - concluded: full STR draft + memo
      - escalated: dossier of unresolved questions, collected evidence, and verbatim critique missing list.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    evidence_sufficient = state.get("evidence_sufficient", False)
    critique_decision = state.get("critique_decision", {})
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)["mock_responses"]
        
    synthesis_fixture = fixtures.get("synthesis", {})
    now = datetime.now(timezone.utc).isoformat()
    
    events = []
    
    if not evidence_sufficient:
        # Branch 1: final_status == escalated
        final_status = "escalated"
        verbatim_missing = critique_decision.get("missing", [])
        
        memo = {
            "disposition": "ESCALATE_TO_OFFICER",
            "summary": synthesis_fixture.get("summary", "Unresolved ambiguity in transaction review."),
            "why_could_not_conclude": verbatim_missing,
            "unresolved_questions": state.get("unresolved_questions", []),
            "evidence_collected": [claim.model_dump() for claim in state.get("claims", [])],
            "claims_count": len(state.get("claims", [])),
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
                "dossier": memo
            },
            timestamp=now
        ))
    else:
        # Branch 2: final_status == concluded
        final_status = "concluded"
        memo = {
            "disposition": "DRAFT_STR",
            "summary": "Compliance violation substantiated by verified claims.",
            "claims": [claim.model_dump() for claim in state.get("claims", [])],
            "generated_at": now
        }
        
        events.append(create_event(
            event_type=EventType.SYNTHESIS_STARTED,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "status": "preparing_str",
                "message": "Evidence sufficient. Drafting Suspicious Transaction Report."
            },
            timestamp=now
        ))
        
        events.append(create_event(
            event_type=EventType.SYNTHESIS_COMPLETE,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "final_status": "concluded",
                "str_draft": memo
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
    memo = state.get("audit_memo", {})
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
            "total_claims_in_ledger": len(state.get("claims", []))
        },
        timestamp=now
    )
    
    return {
        "current_node": "escalate",
        "final_status": "escalated",
        "last_event_sequence": seq + 1,
        "event_log": [event]
    }
