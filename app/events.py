from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class EventType(str, Enum):
    STATE_TRANSITION = "state_transition"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CLAIM_ADDED = "claim_added"
    CLAIM_SUPERSEDED = "claim_superseded"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    UNRESOLVED_ADDED = "unresolved_added"
    ESCALATION = "escalation"
    SYNTHESIS_STARTED = "synthesis_started"
    SYNTHESIS_COMPLETE = "synthesis_complete"

class InvestigationEvent(BaseModel):
    """
    Standardized event schema for audit trail and SSE streaming.
    """
    event_type: EventType
    sequence_number: int
    timestamp: str
    investigation_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)

def create_event(
    event_type: EventType,
    sequence_number: int,
    investigation_id: str,
    payload: Dict[str, Any],
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs a JSON-serializable event dictionary with validated event_type.
    """
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "event_type": event_type.value,
        "sequence_number": sequence_number,
        "timestamp": ts,
        "investigation_id": investigation_id,
        "payload": payload,
    }
