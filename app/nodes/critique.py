import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_case_b.json")

def critique_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Evaluates evidence against hypotheses. Returns a structured critique decision:
    { "sufficient": bool, "reason": str, "missing": [str] }
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    retry_count = state.get("retry_count", 0)
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)["mock_responses"]
        
    now = datetime.now(timezone.utc).isoformat()
    
    if retry_count == 0:
        critique_data = fixtures["iteration_1"]["critique"]
    else:
        critique_data = fixtures["iteration_2"]["critique"]
        
    decision = {
        "sufficient": critique_data["sufficient"],
        "reason": critique_data["reason"],
        "missing": critique_data.get("missing", [])
    }
    
    events = []
    new_unresolved = []
    
    if not decision["sufficient"]:
        events.append(create_event(
            event_type=EventType.EVIDENCE_INSUFFICIENT,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "reason": decision["reason"],
                "missing": decision["missing"],
                "retry_count": retry_count,
                "max_retries": state.get("max_retries", 1)
            },
            timestamp=now
        ))
        
        # Log unresolved questions additions
        if decision["missing"]:
            events.append(create_event(
                event_type=EventType.UNRESOLVED_ADDED,
                sequence_number=seq + 2,
                investigation_id=case_id,
                payload={
                    "unresolved_questions": decision["missing"],
                    "identified_by": "critique",
                    "iteration": retry_count + 1
                },
                timestamp=now
            ))
            new_unresolved = decision["missing"]
    else:
        events.append(create_event(
            event_type=EventType.STATE_TRANSITION,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "decision": "SATISFIED",
                "reason": decision["reason"]
            },
            timestamp=now
        ))
        
    return {
        "current_node": "critique",
        "evidence_sufficient": decision["sufficient"],
        "critique_decision": decision,
        "unresolved_questions": new_unresolved,
        "last_event_sequence": seq + len(events),
        "event_log": events
    }
