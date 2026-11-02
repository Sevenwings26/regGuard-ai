import os
from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event
from app.prompts import (
    RefinePlan,
    REFINE_SYSTEM_PROMPT,
    build_refine_prompt,
    ToolCallSpec
)
from core.llm_adapter import get_llm_provider

def refine_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Consumes structured critique output, increments retry count, and reformulates
    targeted queries to resolve evidence gaps and contradictions.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    retry_count = state.get("retry_count", 0) + 1
    critique_decision = state.get("critique_decision", {})
    missing_items = critique_decision.get("missing", [])
    contradictions = critique_decision.get("detected_contradictions", [])
    tx = state.get("flagged_transaction", {})
    now = datetime.now(timezone.utc).isoformat()

    # 1. Invoke LLM Refine Engine
    llm = get_llm_provider(mode=state.get("mode"))
    prompt = build_refine_prompt(
        critique_decision=critique_decision,
        flagged_tx=tx,
        retry_count=retry_count
    )

    refine_plan: RefinePlan = llm.complete_structured(
        schema=RefinePlan,
        prompt=prompt,
        system=REFINE_SYSTEM_PROMPT
    )

    planned_tool_calls = [call.model_dump() for call in refine_plan.planned_tool_calls]

    # Heuristic fallback if LLM returned empty tool calls but gaps exist
    if not planned_tool_calls:
        tx_date = (tx.get("timestamp") or "")[:10]
        if contradictions or "2021" in tx_date:
            # Temporal contradiction remediation
            planned_tool_calls = [
                {
                    "tool_name": "regulation_search",
                    "parameters": {
                        "query": "corporate cash deposit limit",
                        "effective_before": tx_date
                    }
                },
                {
                    "tool_name": "threshold_calc",
                    "parameters": {
                        "amounts": [float(tx.get("amount", 0))],
                        "timestamps": [tx.get("timestamp", "")],
                        "entity_type": "CORPORATE"
                    }
                }
            ]
        elif missing_items:
            # Secondary attribute / KYC verification
            planned_tool_calls = [
                {
                    "tool_name": "watchlist_lookup",
                    "parameters": {
                        "name": tx.get("customer_name", ""),
                        "dob": tx.get("dob", ""),
                        "nationality": tx.get("nationality", "NGA")
                    }
                }
            ]

    # 2. Emit STATE_TRANSITION event for Refine
    seq += 1
    event = create_event(
        event_type=EventType.STATE_TRANSITION,
        sequence_number=seq,
        investigation_id=case_id,
        payload={
            "from_node": "critique",
            "to_node": "refine",
            "action": refine_plan.action,
            "retry_count": retry_count,
            "targeting_missing_evidence": missing_items,
            "targeting_contradictions": contradictions,
            "reformulated_queries_count": len(planned_tool_calls)
        },
        timestamp=now
    )

    return {
        "current_node": "refine",
        "retry_count": retry_count,
        "planned_queries": planned_tool_calls,
        "last_event_sequence": seq,
        "event_log": [event]
    }
