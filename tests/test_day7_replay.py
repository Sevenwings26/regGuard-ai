import json
import os
import sys
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain
from app.prompts import InvestigationPlan
from core.replay_engine import (
    generate_fixture_key,
    DeterministicReplayMismatchError,
    CachedLLMProvider,
    ReplayStore,
    DEFAULT_REPLAY_FILE
)

def test_generate_fixture_key_determinism():
    """
    Assert that identical inputs produce the identical 64-char hex SHA-256 key
    regardless of dictionary insertion order.
    """
    payload_1 = {"prompt": "Analyze cash structuring", "schema": "InvestigationPlan", "version": 1}
    payload_2 = {"version": 1, "schema": "InvestigationPlan", "prompt": "Analyze cash structuring"}

    key1 = generate_fixture_key("plan", payload_1)
    key2 = generate_fixture_key("plan", payload_2)

    assert len(key1) == 64
    assert key1 == key2, "Canonical JSON sorting failed to produce deterministic key!"

def test_generate_fixture_key_tamper_sensitivity():
    """
    Assert that modifying a single character changes the compound SHA-256 fixture key.
    """
    payload_base = {"prompt": "Customer Musa Ibrahim DOB 1994", "schema": "CritiqueDecision"}
    payload_tampered = {"prompt": "Customer Musa Ibrahim DOB 1995", "schema": "CritiqueDecision"}

    key_base = generate_fixture_key("critique", payload_base)
    key_tampered = generate_fixture_key("critique", payload_tampered)

    assert key_base != key_tampered, "Key generation is insensitive to payload changes!"

def test_replay_mismatch_error_on_unknown_prompt():
    """
    Assert that CachedLLMProvider strictly rejects prompts not present in the replay store,
    throwing DeterministicReplayMismatchError instead of guessing or returning stale state.
    """
    store = ReplayStore(DEFAULT_REPLAY_FILE)
    cached_provider = CachedLLMProvider(replay_store=store)

    unseen_prompt = "Unrecorded prompt for unknown customer X with transaction N100,000,000"

    with pytest.raises(DeterministicReplayMismatchError) as exc_info:
        cached_provider.complete_structured(
            schema=InvestigationPlan,
            prompt=unseen_prompt
        )

    assert "Deterministic replay mismatch" in str(exc_info.value)
    assert "InvestigationPlan" in str(exc_info.value)

def run_cached_case(fixture_filename: str):
    fixture_path = os.path.join(REPO_ROOT, "app", "fixtures", fixture_filename)
    with open(fixture_path, "r", encoding="utf-8") as f:
        case_data = json.load(f)

    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": case_data["case_id"],
        "jurisdiction": case_data.get("jurisdiction", "NGA_CBN"),
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
        "planned_queries": [],
        "mode": "CACHED"
    }

    state = dict(initial_state)
    visited = []
    for step_output in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_update in step_output.items():
            visited.append(node_name)
            for k, v in node_update.items():
                if k in ("claims", "unresolved_questions", "event_log"):
                    state[k] = state.get(k, []) + v
                else:
                    state[k] = v

    return state, visited

def test_cached_mode_case_a_end_to_end():
    """Verify Case A runs entirely through deterministic replay store."""
    final_state, visited = run_cached_case("mock_case_a.json")
    assert visited == ["plan", "act", "critique", "synthesize"]
    assert final_state["final_status"] == "concluded"
    assert final_state["audit_memo"]["disposition"] == "DRAFT_STR"
    is_valid, _ = verify_claims_chain(final_state["claims"])
    assert is_valid is True

def test_cached_mode_case_b_end_to_end():
    """Verify Case B runs entirely through deterministic replay store."""
    final_state, visited = run_cached_case("mock_case_b.json")
    assert visited == ["plan", "act", "critique", "refine", "act", "critique", "synthesize", "escalate"]
    assert final_state["final_status"] == "escalated"
    assert final_state["audit_memo"]["disposition"] == "ESCALATE_TO_OFFICER"
    is_valid, _ = verify_claims_chain(final_state["claims"])
    assert is_valid is True

def test_cached_mode_case_c_end_to_end():
    """Verify Case C runs entirely through deterministic replay store."""
    final_state, visited = run_cached_case("mock_case_c.json")
    assert visited == ["plan", "act", "critique", "refine", "act", "critique", "synthesize"]
    assert final_state["final_status"] == "concluded"
    assert final_state["audit_memo"]["disposition"] == "CLEAR_NO_SUSPICION"
    is_valid, _ = verify_claims_chain(final_state["claims"])
    assert is_valid is True

def test_cached_mode_zero_network_guarantee(monkeypatch):
    """
    Assert that running investigations in CACHED mode makes zero HTTP/network requests.
    Monkeypatches httpx.Client.send to throw an exception if invoked.
    """
    def fail_on_network(*args, **kwargs):
        pytest.fail("Network call attempted during CACHED mode execution!")

    import httpx
    monkeypatch.setattr(httpx.Client, "send", fail_on_network)

    # Execute all 3 cases with network blocked
    for f in ["mock_case_a.json", "mock_case_b.json", "mock_case_c.json"]:
        state, _ = run_cached_case(f)
        assert state["final_status"] in ("concluded", "escalated")
