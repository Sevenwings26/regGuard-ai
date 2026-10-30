from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event

def plan_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Decomposes the flagged transaction into investigative questions and hypotheses.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    tx = state["flagged_transaction"]
    customer = tx.get("customer_name", "Unknown")
    amount = tx.get("amount", 0)
    currency = tx.get("currency", "NGN")
    
    hypotheses = [
        f"Hypothesis 1: Customer {customer} has active PEP exposure violating CBN AML/CFT EDD requirements.",
        f"Hypothesis 2: Inward transaction of {amount:,.2f} {currency} exceeds statutory reporting limits.",
        "Hypothesis 3: Transaction intent lacks underlying economic or commercial substance."
    ]
    
    initial_unresolved = [
        "Verify customer name against PEP/Sanctions watchlist.",
        "Verify secondary KYC identifiers (DOB, BVN, Nationality).",
        "Evaluate statutory reporting threshold under CBN AML Regulations."
    ]
    
    events = [
        create_event(
            event_type=EventType.STATE_TRANSITION,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "from_node": state.get("current_node", "START"),
                "to_node": "plan",
                "hypotheses": hypotheses,
                "message": f"Decomposed transaction for {customer} into {len(hypotheses)} investigative hypotheses."
            }
        ),
        create_event(
            event_type=EventType.UNRESOLVED_ADDED,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "unresolved_questions": initial_unresolved,
                "phase": "initial_planning"
            }
        )
    ]
    
    return {
        "current_node": "plan",
        "unresolved_questions": initial_unresolved,
        "last_event_sequence": seq + len(events),
        "event_log": events,
    }
