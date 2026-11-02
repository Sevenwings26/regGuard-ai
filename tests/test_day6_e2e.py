import json
import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain
from app.events import EventType

def load_case_fixture(filename: str):
    path = os.path.join(REPO_ROOT, "app", "fixtures", filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_case_through_graph(case_data: dict) -> tuple[dict, list[str]]:
    """Runs a case through the compiled StateGraph and records node sequence."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": case_data["case_id"],
        "jurisdiction": case_data["jurisdiction"],
        "flagged_transaction": case_data["flagged_transaction"],
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

    visited_nodes = []
    accumulated_state = dict(initial_state)

    for step_output in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_update in step_output.items():
            visited_nodes.append(node_name)
            for k, v in node_update.items():
                if k in ("claims", "unresolved_questions", "event_log"):
                    accumulated_state[k] = accumulated_state.get(k, []) + v
                else:
                    accumulated_state[k] = v

    return accumulated_state, visited_nodes

def test_case_a_structuring_end_to_end():
    """
    Case A: Structuring cash deposits below N5M aggregating to N5.5M in 25.5h.
    Expected:
      - Path: plan -> act -> critique -> synthesize
      - Retries: 0
      - Final status: concluded
      - Disposition: DRAFT_STR
      - Hash chain: 100% valid SHA-256 chain
      - Monotonic event sequence with zero gaps
    """
    case_data = load_case_fixture("mock_case_a.json")
    final_state, visited_nodes = run_case_through_graph(case_data)

    print("\n--- CASE A END-TO-END VERIFICATION ---")
    print(f"  Visited nodes: {' -> '.join(visited_nodes)}")

    # 1. Routing path verification: direct synthesize without retries
    assert visited_nodes == ["plan", "act", "critique", "synthesize"], (
        f"Unexpected transition path for Case A: {visited_nodes}"
    )

    # 2. State & disposition assertions
    assert final_state["final_status"] == "concluded"
    assert final_state["retry_count"] == 0
    assert final_state["evidence_sufficient"] is True

    memo = final_state["audit_memo"]
    assert memo is not None
    assert memo["disposition"] == "DRAFT_STR"
    assert memo["subject_name"] == "Emeka Okafor"
    assert memo["account_id"] == "ACC-IND-9021"

    draft_str = memo.get("draft_str", {})
    assert draft_str.get("reporting_entity") == "RegGuard Demo Bank Nigeria"
    assert "CBN-AML-2022-SEC-10-3" in draft_str.get("violations_found", [])

    # 3. Evidence Ledger Integrity Check
    claims = final_state["claims"]
    assert len(claims) >= 2, f"Expected at least 2 claims in ledger, got {len(claims)}"
    is_valid, broken_idx = verify_claims_chain(claims)
    assert is_valid is True, f"Hash chain integrity check failed for Case A! Broken at {broken_idx}"

    # 4. Monotonic event sequence check
    events = final_state["event_log"]
    seq_nums = [e["sequence_number"] for e in events]
    assert seq_nums == list(range(1, len(events) + 1)), "Event sequence numbers are not strictly contiguous!"
    print(f"  ✓ Case A passed: {len(claims)} claims verified in hash chain; DRAFT_STR created; {len(events)} events contiguous.")

def test_case_b_pep_demographic_mismatch_end_to_end():
    """
    Case B: PEP name match on watchlist but 33-year DOB mismatch.
    Expected:
      - Path: plan -> act -> critique -> refine -> act -> critique -> synthesize -> escalate
      - Retries: 1
      - Final status: escalated
      - Disposition: ESCALATE_TO_OFFICER
      - Hash chain: 100% valid SHA-256 chain
      - Verbatim missing questions in escalation dossier
    """
    case_data = load_case_fixture("mock_case_b.json")
    final_state, visited_nodes = run_case_through_graph(case_data)

    print("\n--- CASE B END-TO-END VERIFICATION ---")
    print(f"  Visited nodes: {' -> '.join(visited_nodes)}")

    # 1. Routing path verification: must refine, then synthesize, then escalate
    assert visited_nodes == [
        "plan", "act", "critique", "refine", "act", "critique", "synthesize", "escalate"
    ], f"Unexpected transition path for Case B: {visited_nodes}"

    # 2. State & disposition assertions
    assert final_state["final_status"] == "escalated"
    assert final_state["retry_count"] == 1
    assert final_state["evidence_sufficient"] is False

    memo = final_state["audit_memo"]
    assert memo is not None
    assert memo["disposition"] == "ESCALATE_TO_OFFICER"
    assert memo["subject_name"] == "Musa Ibrahim"
    assert len(memo.get("why_could_not_conclude", [])) >= 1
    assert len(memo.get("unresolved_questions", [])) >= 1

    # 3. Escalation event check
    events = final_state["event_log"]
    escalation_events = [e for e in events if e.get("event_type") == EventType.ESCALATION]
    assert len(escalation_events) == 1
    assert escalation_events[0]["payload"]["status"] == "ESCALATED_TO_HUMAN_OFFICER"

    # 4. Evidence Ledger Integrity Check
    claims = final_state["claims"]
    assert len(claims) >= 2
    is_valid, broken_idx = verify_claims_chain(claims)
    assert is_valid is True, f"Hash chain integrity check failed for Case B! Broken at {broken_idx}"

    # 5. Monotonic event sequence check
    seq_nums = [e["sequence_number"] for e in events]
    assert seq_nums == list(range(1, len(events) + 1)), "Event sequence numbers are not strictly contiguous!"
    print(f"  ✓ Case B passed: escalated after retry budget exhausted; dossier intact; {len(events)} events contiguous.")

def test_case_c_temporal_contradiction_resolution_end_to_end():
    """
    Case C: 2021 corporate cash deposit initially citing 2022 regulation.
    Expected:
      - Iteration 1 detects temporal contradiction -> reformulates query with effective_before filter
      - Iteration 2 retrieves 2013 regulation (N10M limit) -> confirms N7.5M is compliant
      - Path: plan -> act -> critique -> refine -> act -> critique -> synthesize
      - Retries: 1
      - Final status: concluded
      - Disposition: CLEAR_NO_SUSPICION
      - Hash chain: 100% valid SHA-256 chain
    """
    case_data = load_case_fixture("mock_case_c.json")
    final_state, visited_nodes = run_case_through_graph(case_data)

    print("\n--- CASE C END-TO-END VERIFICATION ---")
    print(f"  Visited nodes: {' -> '.join(visited_nodes)}")

    # 1. Routing path verification: must refine, then resolve and synthesize to concluded (no escalate)
    assert visited_nodes == [
        "plan", "act", "critique", "refine", "act", "critique", "synthesize"
    ], f"Unexpected transition path for Case C: {visited_nodes}"

    # 2. State & disposition assertions
    assert final_state["final_status"] == "concluded"
    assert final_state["retry_count"] == 1
    assert final_state["evidence_sufficient"] is True

    memo = final_state["audit_memo"]
    assert memo is not None
    assert memo["disposition"] == "CLEAR_NO_SUSPICION"
    assert memo["applicable_regulation"] == "CBN-AML-2013-SEC-02-1"
    assert memo["governing_limit"] == 10000000.0
    assert memo["transaction_amount"] == 7500000.0

    # 3. Evidence Ledger Integrity & Superseded Claim Check
    claims = final_state["claims"]
    assert len(claims) >= 2
    is_valid, broken_idx = verify_claims_chain(claims)
    assert is_valid is True, f"Hash chain integrity check failed for Case C! Broken at {broken_idx}"

    # Verify claim supersession event occurred in event log
    events = final_state["event_log"]
    superseded_events = [e for e in events if e.get("event_type") == EventType.CLAIM_SUPERSEDED]
    assert len(superseded_events) >= 1, "Expected at least one CLAIM_SUPERSEDED event in Case C"

    # 4. Monotonic event sequence check
    seq_nums = [e["sequence_number"] for e in events]
    assert seq_nums == list(range(1, len(events) + 1)), "Event sequence numbers are not strictly contiguous!"
    print(f"  ✓ Case C passed: temporal contradiction resolved; CLEAR_NO_SUSPICION issued; {len(events)} events contiguous.")
