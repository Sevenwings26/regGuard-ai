import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph
from app.state import InvestigationState, verify_claims_chain
from app.events import EventType

CASE_MAP = {
    "A": ("mock_case_a.json", "Case A: Cash Structuring (Triplet deposits totaling N5.5M)"),
    "B": ("mock_case_b.json", "Case B: PEP Watchlist Match (DOB conflict 1994 vs 1961)"),
    "C": ("mock_case_c.json", "Case C: Temporal Alignment (2021 corporate deposit under 2013 rules)")
}

def load_case_fixture(filename: str):
    path = os.path.join(REPO_ROOT, "app", "fixtures", filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_single_case(case_key: str, filename: str, title: str, mode: str = "LIVE"):
    case_data = load_case_fixture(filename)
    tx = case_data["flagged_transaction"]

    print("\n" + "=" * 80)
    print(f" RegGuard AI — Autonomous Compliance Investigation ({mode.upper()} MODE)")
    print(f" {title}")
    print(f" Case ID: {case_data['case_id']} | Customer: {tx.get('customer_name')} | Flag: {tx.get('flag_reason')}")
    print("=" * 80 + "\n")

    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": case_data["case_id"],
        "jurisdiction": case_data.get("jurisdiction", "NGA_CBN"),
        "flagged_transaction": tx,
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
        "mode": mode.upper()
    }

    visited_nodes = []
    accumulated_state = dict(initial_state)

    for step_output in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_update in step_output.items():
            visited_nodes.append(node_name)
            print(f"[NODE ENTER] >>> {node_name.upper()}")

            for k, v in node_update.items():
                if k in ("claims", "unresolved_questions", "event_log"):
                    accumulated_state[k] = accumulated_state.get(k, []) + v
                else:
                    accumulated_state[k] = v

            events = node_update.get("event_log", [])
            for ev in events:
                etype = ev.get("event_type")
                seq = ev.get("sequence_number")
                p = ev.get("payload", {})

                if etype == EventType.TOOL_CALL:
                    print(f"  [EVENT #{seq:02d}: TOOL CALL] -> {p.get('tool')}({p.get('parameters')})")
                elif etype == EventType.TOOL_RESULT:
                    summary = str(p.get("result", {}))
                    if len(summary) > 90:
                        summary = summary[:87] + "..."
                    print(f"  [EVENT #{seq:02d}: TOOL RESULT] <- {summary}")
                elif etype == EventType.CLAIM_ADDED:
                    print(f"  [EVENT #{seq:02d}: CLAIM COMMITTED TO LEDGER]")
                    print(f"    - ID:   {p.get('claim_id')}")
                    print(f"    - Text: {p.get('text')[:85]}...")
                    print(f"    - Hash: {p.get('hash')[:16]}... (prev: {p.get('prev_hash')[:16]}...)")
                elif etype == EventType.CLAIM_SUPERSEDED:
                    print(f"  [EVENT #{seq:02d}: CLAIM SUPERSEDED]")
                    print(f"    - Claim ID: {p.get('superseded_claim_id')}")
                    print(f"    - Reason:   {p.get('reason')}")
                elif etype == EventType.EVIDENCE_INSUFFICIENT:
                    print(f"  [EVENT #{seq:02d}: CRITIQUE FLAGGED INSUFFICIENT / GAP]")
                    print(f"    - Assessment: {p.get('assessment')}")
                    print(f"    - Reason:     {p.get('reason')}")
                    print(f"    - Missing:    {p.get('missing')}")
                elif etype == EventType.SYNTHESIS_STARTED:
                    print(f"  [EVENT #{seq:02d}: SYNTHESIS STARTED - {p.get('status').upper()}]")
                    print(f"    - Message: {p.get('message')}")
                elif etype == EventType.SYNTHESIS_COMPLETE:
                    print(f"  [EVENT #{seq:02d}: SYNTHESIS COMPLETE]")
                    print(f"    - Final Status: {p.get('final_status')} | Disposition: {p.get('disposition')}")
                elif etype == EventType.ESCALATION:
                    print(f"  [EVENT #{seq:02d}: HUMAN COMPLIANCE OFFICER ESCALATION]")
                    print(f"    - Status: {p.get('status')}")
                    print(f"    - Why Unresolved: {p.get('why_could_not_conclude')}")

    transition_path = " -> ".join(visited_nodes)
    print("\n" + "-" * 80)
    print(f"Execution Transition Path: {transition_path}")
    print("-" * 80)

    claims = accumulated_state.get("claims", [])
    events = accumulated_state.get("event_log", [])
    memo = accumulated_state.get("audit_memo", {})
    disposition = memo.get("disposition", "UNKNOWN")
    final_status = accumulated_state.get("final_status")
    retries = accumulated_state.get("retry_count")

    is_chain_valid, broken_idx = verify_claims_chain(claims)
    seq_nums = [e["sequence_number"] for e in events]
    is_seq_monotonic = (seq_nums == list(range(1, len(events) + 1)))

    print("\n[VERIFICATION REPORT]")
    print(f"  1. Final Status:       {final_status.upper()} (Disposition: {disposition})")
    print(f"  2. Retries Utilized:   {retries} / {accumulated_state.get('max_retries')}")
    print(f"  3. Ledger Claims:      {len(claims)} committed claims")
    print(f"  4. Hash Chain Status:  {'✓ INTACT' if is_chain_valid else f'✗ BROKEN at index {broken_idx}'}")
    print(f"  5. Event Log:          {len(events)} events ({'✓ 1..N strictly contiguous' if is_seq_monotonic else '✗ Sequence gap detected'})")

    if disposition == "DRAFT_STR":
        draft_str = memo.get("draft_str", {})
        print(f"\n[SYNTHESIZED DRAFT STR PREVIEW]")
        print(f"  Reporting Entity: {draft_str.get('reporting_entity')}")
        print(f"  Subject:          {draft_str.get('subject_name')} ({draft_str.get('account_id')})")
        print(f"  Violations:       {draft_str.get('violations_found')}")
        print(f"  Statutory Clause: {draft_str.get('statutory_violation')}")
        print(f"  Ledger Tip Hash:  {draft_str.get('ledger_tip_hash')}")
        print(f"  Filing Deadline:  {draft_str.get('filing_deadline')}")
    elif disposition == "ESCALATE_TO_OFFICER":
        print(f"\n[ESCALATION DOSSIER PREVIEW]")
        print(f"  Subject:            {memo.get('subject_name')} ({memo.get('account_id')})")
        print(f"  Why Unresolved:     {memo.get('why_could_not_conclude')}")
        print(f"  Unresolved Gaps:    {memo.get('unresolved_questions')}")
        print(f"  Recommended Action: {memo.get('recommended_officer_action')}")
        print(f"  Ledger Tip Hash:    {memo.get('ledger_tip_hash')}")
    elif disposition == "CLEAR_NO_SUSPICION":
        print(f"\n[CLEARANCE CERTIFICATE PREVIEW]")
        print(f"  Subject:            {memo.get('subject_name')} ({memo.get('account_id')})")
        print(f"  Applicable Reg:     {memo.get('applicable_regulation')}")
        print(f"  Governing Limit:    NGN {memo.get('governing_limit'):,.2f}")
        print(f"  Deposit Amount:     NGN {memo.get('transaction_amount'):,.2f}")
        print(f"  Compliance Reason:  {memo.get('cleared_reason')}")
        print(f"  Recommended Action: {memo.get('recommended_action')}")

    return {
        "case_key": case_key,
        "case_id": case_data["case_id"],
        "transition_path": transition_path,
        "final_status": final_status,
        "disposition": disposition,
        "retries": retries,
        "claims_count": len(claims),
        "chain_valid": is_chain_valid,
        "seq_valid": is_seq_monotonic
    }

def main():
    parser = argparse.ArgumentParser(description="RegGuard AI — Multi-Case CLI Demonstration Harness")
    parser.add_argument("--case", choices=["A", "B", "C", "all"], default="all", help="Case to execute (A, B, C, or all)")
    parser.add_argument("--mode", choices=["LIVE", "CACHED"], default="LIVE", help="Execution mode (LIVE with model adapter, or CACHED with deterministic replay)")
    args = parser.parse_args()

    selected = ["A", "B", "C"] if args.case == "all" else [args.case.upper()]
    results = []

    for k in selected:
        fn, desc = CASE_MAP[k]
        res = run_single_case(k, fn, desc, mode=args.mode)
        results.append(res)

    print("\n" + "=" * 90)
    print(" REGGUARD AI — MULTI-CASE HACKATHON BENCHMARK SUMMARY")
    print("=" * 90)
    print(f"{'Case':<8} {'Case ID':<22} {'Disposition':<22} {'Retries':<9} {'Ledger':<12} {'Chain':<10}")
    print("-" * 90)
    for r in results:
        chain_txt = "VALID" if r["chain_valid"] else "BROKEN"
        print(f"{r['case_key']:<8} {r['case_id']:<22} {r['disposition']:<22} {r['retries']:<9} {r['claims_count']:<12} {chain_txt:<10}")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    main()
