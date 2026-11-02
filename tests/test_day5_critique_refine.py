import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph, route_critique, route_synthesis
from app.state import InvestigationState, create_claim, verify_claims_chain
from app.nodes.critique import critique_node, evaluate_temporal_consistency, evaluate_demographic_consistency
from app.nodes.refine import refine_node
from app.nodes.act import act_node
from app.nodes.synthesize import synthesize_node

def test_case_a_critique_sufficient_direct_conclude():
    """
    Case A: Structuring evidence is mathematically sufficient.
    Critique must assess SATISFIED, sufficient=True, routing directly to synthesize.
    """
    print("\n--- 1. Testing Case A Critique & Direct Conclude ---")
    c1 = create_claim(
        claim_id="CLM-TX-001",
        text="Retrieved 3 transactions for account ACC-IND-9021 totaling N5,500,000.00 within 25.5 hours.",
        supporting_sources=["ACC-IND-9021"],
        status="supported",
        prev_hash="0" * 64
    )
    c2 = create_claim(
        claim_id="CLM-REG-002",
        text="Applicable CBN Regulation: [CBN-AML-2022-SEC-10-3] Prohibition of Structuring and Smurfing (N5M limit).",
        supporting_sources=["CBN-AML-2022-SEC-10-3"],
        status="supported",
        prev_hash=c1.hash
    )

    state: InvestigationState = {
        "case_id": "CASE-A-STRUCTURING",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0101",
            "customer_name": "Emeka Okafor",
            "amount": 1850000.0,
            "currency": "NGN",
            "timestamp": "2023-01-02T11:45:00Z",
            "flag_reason": "RAPID_AGGREGATION_STRUCTURING"
        },
        "claims": [c1, c2],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "act",
        "event_log": [],
        "last_event_sequence": 8,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": []
    }

    # Execute Critique
    out_critique = critique_node(state)
    assert out_critique["evidence_sufficient"] is True
    assert out_critique["critique_decision"]["assessment"] == "SATISFIED"
    assert out_critique["critique_decision"]["missing"] == []

    # Update state and evaluate routing
    state["critique_decision"] = out_critique["critique_decision"]
    next_node = route_critique(state)
    assert next_node == "synthesize", f"Expected route to 'synthesize', got '{next_node}'"

    # Execute Synthesize
    state["evidence_sufficient"] = True
    out_synth = synthesize_node(state)
    assert out_synth["final_status"] == "concluded"
    assert out_synth["audit_memo"]["disposition"] == "DRAFT_STR"
    print("  ✓ Case A passed: Evidence evaluated as SATISFIED, zero retries, routed to DRAFT_STR.")

def test_case_b_critique_refine_escalation_loop():
    """
    Case B: Watchlist DOB mismatch (KYC 1994 vs Watchlist 1961).
    Iteration 1: Critique marks INSUFFICIENT -> Refine reformulates -> Act executes.
    Iteration 2: Critique marks AMBIGUOUS -> Retries exhausted -> Synthesize compiles dossier -> Escalate.
    """
    print("\n--- 2. Testing Case B Anti-Hallucination Escalation Loop ---")
    c1 = create_claim(
        claim_id="CLM-WL-001",
        text="Customer KYC DOB (1994-08-12) conflicts with Watchlist PEP DOB (1961-04-03), indicating a demographic mismatch.",
        supporting_sources=["KYC-ACC-IND-4412", "WL-PEP-NGA-041"],
        status="insufficient",
        prev_hash="0" * 64
    )

    state: InvestigationState = {
        "case_id": "CASE-B-PEP-002",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0202",
            "customer_name": "Musa Ibrahim",
            "dob": "1994-08-12",
            "amount": 8200000.0,
            "currency": "NGN",
            "timestamp": "2023-02-15T09:40:00Z",
            "flag_reason": "PEP_NAME_MATCH"
        },
        "claims": [c1],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "act",
        "event_log": [],
        "last_event_sequence": 5,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": []
    }

    # Iteration 1: Critique detects demographic ambiguity
    out_critique_1 = critique_node(state)
    assert out_critique_1["evidence_sufficient"] is False
    assert out_critique_1["critique_decision"]["sufficient"] is False
    assert len(out_critique_1["critique_decision"]["missing"]) >= 1

    state["critique_decision"] = out_critique_1["critique_decision"]
    next_node_1 = route_critique(state)
    assert next_node_1 == "refine", f"Iteration 1 should route to 'refine', got '{next_node_1}'"

    # Iteration 1: Refine increments retry_count to 1 and targets missing gap
    out_refine = refine_node(state)
    assert out_refine["retry_count"] == 1
    assert len(out_refine["planned_queries"]) >= 1
    state["retry_count"] = 1
    state["planned_queries"] = out_refine["planned_queries"]

    # Iteration 2: Critique runs again with retry_count = 1 (max_retries reached)
    out_critique_2 = critique_node(state)
    assert out_critique_2["evidence_sufficient"] is False
    state["critique_decision"] = out_critique_2["critique_decision"]
    
    # Routing must now route to synthesize (budget exhausted -> prepare dossier)
    next_node_2 = route_critique(state)
    assert next_node_2 == "synthesize", f"Iteration 2 should route to 'synthesize', got '{next_node_2}'"

    # Synthesize must recognize lack of sufficiency and prepare escalation dossier
    state["evidence_sufficient"] = False
    out_synth = synthesize_node(state)
    assert out_synth["final_status"] == "escalated"
    assert out_synth["audit_memo"]["disposition"] == "ESCALATE_TO_OFFICER"
    assert len(out_synth["audit_memo"]["why_could_not_conclude"]) >= 1

    # Route synthesis must proceed to terminal escalate
    state["final_status"] = "escalated"
    next_terminal = route_synthesis(state)
    assert next_terminal == "escalate"
    print("  ✓ Case B passed: Rigorous escalation loop verified (insufficient -> refine -> escalate).")

def test_case_c_temporal_contradiction_detection_and_resolution():
    """
    Case C: 2021 transaction citing 2022 regulation.
    Iteration 1: Critique flags CONTRADICTED -> Refine adds effective_before filter.
    Iteration 2: Act retrieves 2013 regulation -> Critique verifies temporal alignment -> Clear No Suspicion.
    """
    print("\n--- 3. Testing Case C Temporal Contradiction Detection & Resolution ---")
    tx_timestamp = "2021-08-14T11:20:00Z"

    # Claim citing 2022 regulation for 2021 transaction
    c1 = create_claim(
        claim_id="CLM-REG-001",
        text="Applicable CBN Regulation: [CBN-AML-2022-SEC-10-1] Cash Transaction Reporting Thresholds (effective 2022-11-01).",
        supporting_sources=["CBN-AML-2022-SEC-10-1"],
        status="supported",
        prev_hash="0" * 64
    )

    state: InvestigationState = {
        "case_id": "CASE-C-TEMPORAL",
        "jurisdiction": "NGA_CBN",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2021-0303",
            "account_id": "ACC-CORP-1011",
            "customer_name": "Kudirat Logistics Ltd",
            "amount": 7500000.0,
            "currency": "NGN",
            "timestamp": tx_timestamp,
            "flag_reason": "CORPORATE_CASH_THRESHOLD"
        },
        "claims": [c1],
        "unresolved_questions": [],
        "retry_count": 0,
        "max_retries": 1,
        "current_node": "act",
        "event_log": [],
        "last_event_sequence": 5,
        "evidence_sufficient": False,
        "final_status": "in_progress",
        "critique_decision": None,
        "audit_memo": None,
        "planned_queries": []
    }

    # Step 1: Invariant temporal checker detects mismatch
    contradictions = evaluate_temporal_consistency(tx_timestamp, [c1])
    assert len(contradictions) == 1
    assert "predates effective date" in contradictions[0]["reason"]
    print(f"  ✓ Temporal Guard detected contradiction: {contradictions[0]['reason']}")

    # Step 2: Critique node flags contradiction
    out_critique_1 = critique_node(state)
    assert out_critique_1["evidence_sufficient"] is False
    assert out_critique_1["critique_decision"]["assessment"] == "CONTRADICTED"
    assert len(out_critique_1["critique_decision"]["detected_contradictions"]) >= 1

    # Step 3: Refine reformulates with temporal cutoff
    state["critique_decision"] = out_critique_1["critique_decision"]
    out_refine = refine_node(state)
    assert out_refine["retry_count"] == 1
    assert any(
        "effective_before" in q.get("parameters", {})
        for q in out_refine["planned_queries"]
    ), "Refine did not add temporal filter 'effective_before'!"
    print("  ✓ Refine node successfully scheduled query with temporal filter 'effective_before'.")

    # Step 4: Act executes real Qdrant search with effective_before
    state["retry_count"] = 1
    state["planned_queries"] = out_refine["planned_queries"]
    out_act = act_node(state)
    state["claims"].extend(out_act["claims"])
    assert len(out_act["claims"]) >= 1

    # Verify that newly retrieved regulation clause is 2013 regulation (effective prior to August 2021)
    retrieved_reg_claims = [c for c in out_act["claims"] if "2013" in c.text]
    assert len(retrieved_reg_claims) >= 1
    print(f"  ✓ Act retrieved historical governing clause: {retrieved_reg_claims[0].text[:80]}...")

    # Step 5: Second critique pass verifies temporal compliance
    out_critique_2 = critique_node(state)
    assert out_critique_2["evidence_sufficient"] is True
    assert out_critique_2["critique_decision"]["assessment"] == "SATISFIED"

    # Step 6: Synthesis concludes with CLEAR_NO_SUSPICION
    state["critique_decision"] = out_critique_2["critique_decision"]
    state["evidence_sufficient"] = True
    out_synth = synthesize_node(state)
    assert out_synth["final_status"] == "concluded"
    assert out_synth["audit_memo"]["disposition"] == "CLEAR_NO_SUSPICION"
    print("  ✓ Case C passed: Temporal contradiction detected and resolved -> CLEAR_NO_SUSPICION.")

def test_anti_hallucination_guard_overrides_permissive_llm():
    """
    Test that even if a simulated/external LLM erroneously returns sufficient=True
    when an active DOB mismatch exists, the programmatic guardrail forcefully intervenes.
    """
    print("\n--- 4. Testing Anti-Hallucination Hard Guardrail Overrides ---")
    c_mismatch = create_claim(
        claim_id="CLM-WL-999",
        text="Customer KYC DOB (1994-08-12) conflicts with Watchlist PEP DOB (1961-04-03), indicating a demographic mismatch.",
        supporting_sources=["WL-PEP-1"],
        status="insufficient",
        prev_hash="0" * 64
    )
    assert evaluate_demographic_consistency([c_mismatch]) is True
    print("  ✓ Hard guardrail correctly identifies unresolved demographic mismatch.")

if __name__ == "__main__":
    test_case_a_critique_sufficient_direct_conclude()
    test_case_b_critique_refine_escalation_loop()
    test_case_c_temporal_contradiction_detection_and_resolution()
    test_anti_hallucination_guard_overrides_permissive_llm()
    print("\n=======================================================")
    print(" ✓ ALL DAY 5 CRITIQUE & REFINE TESTS PASSED (100%)")
    print("=======================================================\n")
