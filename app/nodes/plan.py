from datetime import datetime, timezone
from typing import Any, Dict
from app.state import InvestigationState
from app.events import EventType, create_event
from app.prompts import InvestigationPlan, PLAN_SYSTEM_PROMPT, build_plan_prompt
from core.llm_adapter import get_llm_provider

def plan_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Decomposes the flagged transaction into investigative hypotheses and schedules
    initial tool calls using LLM reasoning.
    """
    case_id = state["case_id"]
    seq = state.get("last_event_sequence", 0)
    tx = state["flagged_transaction"]
    customer = tx.get("customer_name", "Unknown")
    
    # 1. Invoke LLM structured plan generator
    llm = get_llm_provider(mode=state.get("mode"))
    prompt = build_plan_prompt(tx, state.get("jurisdiction", "NGA_CBN"))
    plan: InvestigationPlan = llm.complete_structured(
        schema=InvestigationPlan,
        prompt=prompt,
        system=PLAN_SYSTEM_PROMPT
    )
    
    events = [
        create_event(
            event_type=EventType.STATE_TRANSITION,
            sequence_number=seq + 1,
            investigation_id=case_id,
            payload={
                "from_node": state.get("current_node", "START"),
                "to_node": "plan",
                "provider": llm.provider_name,
                "hypotheses": plan.hypotheses,
                "message": f"Decomposed transaction for {customer} into {len(plan.hypotheses)} investigative hypotheses."
            }
        ),
        create_event(
            event_type=EventType.UNRESOLVED_ADDED,
            sequence_number=seq + 2,
            investigation_id=case_id,
            payload={
                "unresolved_questions": plan.initial_questions,
                "phase": "initial_planning"
            }
        )
    ]
    
    return {
        "current_node": "plan",
        "unresolved_questions": plan.initial_questions,
        "planned_queries": [call.model_dump() for call in plan.planned_tool_calls],
        "last_event_sequence": seq + len(events),
        "event_log": events,
    }
