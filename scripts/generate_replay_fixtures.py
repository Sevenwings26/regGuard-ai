import json
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain
from core.llm_adapter import get_llm_provider
from core.replay_engine import (
    ReplayStore,
    RecordingLLMProvider,
    CachedLLMProvider,
    DEFAULT_REPLAY_DIR,
    DEFAULT_REPLAY_FILE
)

CASES = [
    ("Case A", "mock_case_a.json", "case_a_fixtures.json"),
    ("Case B", "mock_case_b.json", "case_b_fixtures.json"),
    ("Case C", "mock_case_c.json", "case_c_fixtures.json"),
]

def generate_fixtures():
    print("\n" + "=" * 80)
    print(" RegGuard AI — Deterministic Replay Fixture Generator")
    print(" Recording live/mock execution into tamper-verified replay store")
    print("=" * 80 + "\n")

    os.makedirs(DEFAULT_REPLAY_DIR, exist_ok=True)
    master_store = ReplayStore(DEFAULT_REPLAY_FILE)

    # Use Recording provider wrapping the active provider
    base_provider = get_llm_provider()
    recording_provider = RecordingLLMProvider(base_provider, master_store)
    from core.llm_adapter import set_provider_override
    set_provider_override(recording_provider)

    graph = build_investigation_graph()

    for label, fixture_file, case_out_file in CASES:
        print(f"[RECORDING] {label} ({fixture_file})...")
        fixture_path = os.path.join(REPO_ROOT, "app", "fixtures", fixture_file)
        with open(fixture_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)
        tx = case_data["flagged_transaction"]

        before_count = len(master_store)
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
            "planned_queries": []
        }

        # Step through graph and accumulate
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

        added = len(master_store) - before_count
        print(f"  ✓ {label} recorded {added} LLM interactions.")
        print(f"  ✓ Transition sequence: {' -> '.join(visited)}")
        print(f"  ✓ Final status: {state.get('final_status')} | Disposition: {state.get('audit_memo', {}).get('disposition')}")

        # Export individual case fixture file
        case_store_path = os.path.join(DEFAULT_REPLAY_DIR, case_out_file)
        cname = tx.get("customer_name", "").lower()
        acc = tx.get("account_id", "").lower()
        cid = case_data["case_id"].lower()
        case_entries = {
            k: v for k, v in master_store._entries.items()
            if (cid in json.dumps(v).lower() or cname in json.dumps(v).lower() or acc in json.dumps(v).lower())
        }
        with open(case_store_path, "w", encoding="utf-8") as f:
            json.dump(case_entries, f, indent=2, sort_keys=True)
        print(f"  ✓ Written individual case fixtures: {case_out_file} ({len(case_entries)} entries)")

    # Remove recording override and save master store
    set_provider_override(None)
    master_store.save()
    print(f"\n[MASTER STORE] Saved {len(master_store)} total deterministic replay fixtures to:")
    print(f"  {DEFAULT_REPLAY_FILE}")

    # Step 2: Verification Run using pure CachedLLMProvider
    print("\n" + "-" * 80)
    print(" Verifying Deterministic Replay Execution (Zero Network / 100% Cache Hits)")
    print("-" * 80)

    cached_provider = CachedLLMProvider(master_store)
    set_provider_override(cached_provider)

    for label, fixture_file, _ in CASES:
        fixture_path = os.path.join(REPO_ROOT, "app", "fixtures", fixture_file)
        with open(fixture_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)
        tx = case_data["flagged_transaction"]

        initial_state = {
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

        is_valid, _ = verify_claims_chain(state["claims"])
        assert is_valid is True, f"Hash chain broken during cached replay of {label}!"
        print(f"  ✓ {label} Replay PASSED: {' -> '.join(visited)} (Ledger Chain: VALID)")

    set_provider_override(None)
    print("\n✓ ALL REPLAY FIXTURES GENERATED AND VERIFIED SUCCESSFULLY.\n")

if __name__ == "__main__":
    generate_fixtures()
