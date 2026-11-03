import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.llm_adapter import get_llm_provider, MockLLMProvider
from app.prompts import InvestigationPlan, ToolCallSpec
from app.nodes.plan import plan_node
from app.nodes.act import act_node
from app.state import InvestigationState, verify_claims_chain

def test_llm_adapter_structured_completion():
    print("\n--- 1. Testing LLM Provider Adapter ---")
    provider = get_llm_provider()
    assert provider is not None
    assert any(m in provider.provider_name.lower() for m in ["llama", "mock", "meta"])

    prompt = "Case B: Musa Ibrahim inward transfer N8,200,000 flagged for PEP."
    plan = provider.complete_structured(InvestigationPlan, prompt)
    assert isinstance(plan, InvestigationPlan)
    assert len(plan.hypotheses) >= 2
    assert len(plan.planned_tool_calls) >= 1
    assert any(c.tool_name == "watchlist_lookup" for c in plan.planned_tool_calls)
    print(f"  ✓ Adapter [{provider.provider_name}] returned structured plan with {len(plan.hypotheses)} hypotheses.")

def test_plan_node_execution():
    print("\n--- 2. Testing Plan Node Execution ---")
    state: InvestigationState = {
        "case_id": "CASE-A-STRUCTURING",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0101",
            "account_id": "ACC-IND-9021",
            "customer_name": "Emeka Okafor",
            "dob": "1985-06-20",
            "amount": 1850000.0,
            "currency": "NGN",
            "timestamp": "2023-01-02 11:45:00",
            "flag_reason": "RAPID_AGGREGATION_STRUCTURING"
        },
        "claims": [],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "START",
        "event_log": [],
        "last_event_sequence": 0,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": []
    }

    output = plan_node(state)
    assert output["current_node"] == "plan"
    assert len(output["unresolved_questions"]) >= 2
    assert len(output["planned_queries"]) >= 1
    assert output["last_event_sequence"] == 2
    assert len(output["event_log"]) == 2
    print(f"  ✓ Plan node produced {len(output['planned_queries'])} planned queries and logged {len(output['event_log'])} events.")

def test_act_node_dynamic_dispatch_and_ledger():
    print("\n--- 3. Testing Act Node Dynamic Tool Dispatch & Evidence Ledger ---")
    state: InvestigationState = {
        "case_id": "CASE-A-STRUCTURING",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0101",
            "account_id": "ACC-IND-9021",
            "customer_name": "Emeka Okafor",
            "dob": "1985-06-20",
            "amount": 1850000.0,
            "currency": "NGN",
            "timestamp": "2023-01-02 11:45:00",
            "flag_reason": "RAPID_AGGREGATION_STRUCTURING"
        },
        "claims": [],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "plan",
        "event_log": [],
        "last_event_sequence": 2,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": [
            {
                "tool_name": "query_transactions",
                "parameters": {
                    "sql_query": "SELECT * FROM transactions WHERE account_id = 'ACC-IND-9021' ORDER BY timestamp ASC;"
                }
            },
            {
                "tool_name": "regulation_search",
                "parameters": {
                    "query": "prohibition of structuring and smurfing cash deposits",
                    "top_k": 1
                }
            }
        ]
    }

    output = act_node(state)
    assert output["current_node"] == "act"
    assert len(output["claims"]) == 2
    assert output["planned_queries"] == []  # Successfully consumed
    
    # Verify hash chain across claims
    intact, broken_idx = verify_claims_chain(output["claims"])
    assert intact is True
    assert output["claims"][0].prev_hash == "0" * 64
    assert output["claims"][1].prev_hash == output["claims"][0].hash

    # Check events sequence
    events = output["event_log"]
    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "claim_added" in event_types
    assert output["last_event_sequence"] == 2 + len(events)
    print(f"  ✓ Act node executed 2 real tools, created 2 SHA-256 chained claims, and emitted {len(events)} events.")

def test_act_node_ast_guard_resilience():
    print("\n--- 4. Testing Act Node AST Guard Protection Against Malicious SQL ---")
    state: InvestigationState = {
        "case_id": "TEST-ATTACK",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {"account_id": "ACC-1"},
        "claims": [],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "plan",
        "event_log": [],
        "last_event_sequence": 0,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": [
            {
                "tool_name": "query_transactions",
                "parameters": {
                    "sql_query": "DROP TABLE transactions;"
                }
            }
        ]
    }

    output = act_node(state)
    # The tool should have safely caught the AST violation in result and not committed unsafe claims
    tool_results = [e for e in output["event_log"] if e["event_type"] == "tool_result"]
    assert len(tool_results) == 1
    assert "error" in tool_results[0]["payload"]["result"]
    assert "Forbidden statement type" in tool_results[0]["payload"]["result"]["error"]
    print("  ✓ Malicious SQL was intercepted by AST Guard and safely quarantined in event log.")

if __name__ == "__main__":
    test_llm_adapter_structured_completion()
    test_plan_node_execution()
    test_act_node_dynamic_dispatch_and_ledger()
    test_act_node_ast_guard_resilience()
    print("\n✓ ALL DAY 4 UNIT & INTEGRATION CHECKS PASSED (100%)\n")
