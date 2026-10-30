import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_case_b.json")

def refine_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Consumes structured critique output, increments retry count, and reformulates queries.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    retry_count = state.get("retry_count", 0) + 1
    critique_decision = state.get("critique_decision", {})
    missing_items = critique_decision.get("missing", [])
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)["mock_responses"]
        
    refine_action = fixtures.get("iteration_1", {}).get("refine", {}).get(
        "action", 
        f"Reformulating queries to resolve missing evidence: {missing_items}"
    )
    
    now = datetime.now(timezone.utc).isoformat()
    event = create_event(
        event_type=EventType.STATE_TRANSITION,
        sequence_number=seq + 1,
        investigation_id=case_id,
        payload={
            "from_node": "critique",
            "to_node": "refine",
            "action": refine_action,
            "retry_count": retry_count,
            "targeting_missing_evidence": missing_items
        },
        timestamp=now
    )
    
    return {
        "current_node": "refine",
        "retry_count": retry_count,
        "last_event_sequence": seq + 1,
        "event_log": [event]
    }
