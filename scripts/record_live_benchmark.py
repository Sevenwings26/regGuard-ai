import json
import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain
from core.llm_adapter import get_llm_provider, get_last_llm_latency

BENCHMARK_DIR = os.path.join(REPO_ROOT, "data", "live_benchmark_logs")

CASES = [
    ("CASE-A-STRUCTURING", "mock_case_a.json"),
    ("CASE-B-PEP-002", "mock_case_b.json"),
    ("CASE-C-TEMPORAL", "mock_case_c.json"),
]

def run_live_benchmark():
    os.makedirs(BENCHMARK_DIR, exist_ok=True)
    provider = get_llm_provider(mode="LIVE")
    print("=" * 80)
    print(" RegGuard AI — Live Provider Audit & Benchmark Trace")
    print(f" Active Provider: {provider.provider_name}")
    print("=" * 80)

    graph = build_investigation_graph()

    summary_records = []

    for case_id, fixture_file in CASES:
        fixture_path = os.path.join(REPO_ROOT, "app", "fixtures", fixture_file)
        with open(fixture_path, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        print(f"\n[EXECUTING LIVE] {case_id} ({fixture_file})...")
        t0 = time.perf_counter()

        initial_state: InvestigationState = {
            "case_id": case_id,
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
            "mode": "LIVE"
        }

        state = dict(initial_state)
        node_latencies = {}
        visited = []

        for step_output in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_update in step_output.items():
                visited.append(node_name)
                lat = get_last_llm_latency()
                if lat:
                    node_latencies[node_name] = lat
                for k, v in node_update.items():
                    if k in ("claims", "unresolved_questions", "event_log"):
                        state[k] = state.get(k, []) + v
                    else:
                        state[k] = v

        total_duration = round((time.perf_counter() - t0) * 1000, 2)
        chain_valid, broken_idx = verify_claims_chain(state.get("claims", []))

        memo = state.get("audit_memo", {}) or {}
        disp = memo.get("disposition", "UNKNOWN")
        model = memo.get("model_name", provider.provider_name)

        print(f"  ✓ Transitions: {' -> '.join(visited)}")
        print(f"  ✓ Terminal Disposition: {disp}")
        print(f"  ✓ Cryptographic Ledger: {'VALID' if chain_valid else 'BROKEN'} ({len(state.get('claims', []))} claims)")
        print(f"  ✓ Total Wall Clock: {total_duration}ms")

        # Save benchmark log
        log_path = os.path.join(BENCHMARK_DIR, f"{case_id.lower()}_live.json")
        record = {
            "case_id": case_id,
            "provider": provider.provider_name,
            "model_name": model,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_latency_ms": total_duration,
            "node_latencies_ms": node_latencies,
            "visited_nodes": visited,
            "terminal_disposition": disp,
            "final_status": state.get("final_status"),
            "ledger_chain_valid": chain_valid,
            "claims_count": len(state.get("claims", [])),
            "tip_hash": state.get("claims", [])[-1].hash if state.get("claims") else "0" * 64,
            "summary": memo.get("summary", "")
        }
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
        print(f"  ✓ Saved benchmark record to: {log_path}")

        summary_records.append(record)

    print("\n" + "=" * 80)
    print(" LIVE BENCHMARK SUMMARY")
    print("=" * 80)
    for r in summary_records:
        print(f"- {r['case_id']}: {r['terminal_disposition']} via [{r['provider']}] in {r['total_latency_ms']}ms (Chain: {r['ledger_chain_valid']})")

if __name__ == "__main__":
    run_live_benchmark()
