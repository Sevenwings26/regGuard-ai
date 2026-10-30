import json
import os
from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState, create_claim
from app.events import EventType, create_event

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_case_b.json")

def act_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Executes mock evidence retrieval and appends tamper-evident claims to the ledger.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    retry_count = state.get("retry_count", 0)
    existing_claims = state.get("claims", [])
    
    # Establish previous hash for chain continuity
    prev_hash = existing_claims[-1].hash if existing_claims else "0" * 64
    
    # Load mock fixtures
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)["mock_responses"]
        
    new_claims = []
    events = []
    now = datetime.now(timezone.utc).isoformat()
    
    if retry_count == 0:
        # First act: Watchlist lookup returns name similarity 0.87
        mock_data = fixtures["iteration_1"]["act"]
        claim = create_claim(
            claim_id="CLM-WL-001",
            text=mock_data["claim_text"],
            supporting_sources=mock_data["supporting_sources"],
            status="supported",
            prev_hash=prev_hash,
            timestamp=now
        )
        new_claims.append(claim)
        
        events.append(create_event(
            event_type=EventType.TOOL_CALL,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "tool": mock_data["tool"],
                "node": "act",
                "parameters": {"name": state["flagged_transaction"]["customer_name"]}
            },
            timestamp=now
        ))
        events.append(create_event(
            event_type=EventType.TOOL_RESULT,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "tool": mock_data["tool"],
                "result": mock_data["result"]
            },
            timestamp=now
        ))
        events.append(create_event(
            event_type=EventType.CLAIM_ADDED,
            sequence_number=seq + 3,
            investigation_id=case_id,
            payload={
                "claim_id": claim.claim_id,
                "text": claim.text,
                "status": claim.status,
                "hash": claim.hash,
                "prev_hash": claim.prev_hash
            },
            timestamp=now
        ))
    else:
        # Second act: DOB verification exposes 33-year discrepancy
        mock_data = fixtures["iteration_2"]["act"]
        claim = create_claim(
            claim_id="CLM-KYC-002",
            text=mock_data["claim_text"],
            supporting_sources=mock_data["supporting_sources"],
            status="insufficient",
            prev_hash=prev_hash,
            timestamp=now
        )
        new_claims.append(claim)
        
        events.append(create_event(
            event_type=EventType.TOOL_CALL,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "tool": mock_data["tool"],
                "node": "act",
                "parameters": {
                    "account_id": state["flagged_transaction"]["account_id"],
                    "verify_fields": ["dob", "bvn", "nationality"]
                }
            },
            timestamp=now
        ))
        events.append(create_event(
            event_type=EventType.TOOL_RESULT,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "tool": mock_data["tool"],
                "result": mock_data["result"]
            },
            timestamp=now
        ))
        events.append(create_event(
            event_type=EventType.CLAIM_ADDED,
            sequence_number=seq + 3,
            investigation_id=case_id,
            payload={
                "claim_id": claim.claim_id,
                "text": claim.text,
                "status": claim.status,
                "hash": claim.hash,
                "prev_hash": claim.prev_hash
            },
            timestamp=now
        ))

    return {
        "current_node": "act",
        "claims": new_claims,
        "last_event_sequence": seq + len(events),
        "event_log": events
    }
