from typing import Literal
from langgraph.graph import END, START, StateGraph
from app.state import InvestigationState
from app.nodes.plan import plan_node
from app.nodes.act import act_node
from app.nodes.critique import critique_node
from app.nodes.refine import refine_node
from app.nodes.synthesize import synthesize_node, escalate_node

def route_critique(state: InvestigationState) -> Literal["refine", "synthesize"]:
    """
    Evaluates structured critique decision:
      - If insufficient and retries remain -> refine
      - If sufficient OR retry limit reached -> synthesize
        (When retries are exhausted, synthesize prepares the escalation dossier).
    """
    decision = state.get("critique_decision", {})
    sufficient = decision.get("sufficient", False)
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)
    
    if not sufficient and retry_count < max_retries:
        return "refine"
    
    return "synthesize"

def route_synthesis(state: InvestigationState) -> Literal["escalate", "__end__"]:
    """escalate is only reachable via synthesize; synthesize is always visited before terminal state (concluded or escalated)."""
    if state.get("final_status") == "escalated":
        return "escalate"
    return END

def build_investigation_graph():
    """
    Constructs and compiles the RegGuard LangGraph state machine.
    """
    workflow = StateGraph(InvestigationState)
    
    # Register nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("act", act_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("refine", refine_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("escalate", escalate_node)
    
    # Wire edges
    workflow.add_edge(START, "plan")
    workflow.add_edge("plan", "act")
    workflow.add_edge("act", "critique")
    
    workflow.add_conditional_edges(
        "critique",
        route_critique,
        {
            "refine": "refine",
            "synthesize": "synthesize"
        }
    )
    
    workflow.add_edge("refine", "act")
    
    workflow.add_conditional_edges(
        "synthesize",
        route_synthesis,
        {
            "escalate": "escalate",
            "__end__": END
        }
    )
    
    workflow.add_edge("escalate", END)
    
    return workflow.compile()
