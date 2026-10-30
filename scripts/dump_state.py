import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.graph import build_investigation_graph

with open("app/fixtures/mock_case_b.json", "r", encoding="utf-8") as f:
    case_data = json.load(f)

init_state = {
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
}

g = build_investigation_graph()
final_s = g.invoke(init_state)

excerpt = {
    "case_id": final_s["case_id"],
    "final_status": final_s["final_status"],
    "retry_count": final_s["retry_count"],
    "claims": [c.model_dump() for c in final_s["claims"]],
    "unresolved_questions": final_s["unresolved_questions"],
    "event_log": [
        {
            "sequence_number": e["sequence_number"],
            "event_type": e["event_type"],
            "timestamp": e["timestamp"],
            "investigation_id": e["investigation_id"],
            "payload": e["payload"]
        }
        for e in final_s["event_log"]
    ],
    "audit_memo": final_s["audit_memo"]
}

print(json.dumps(excerpt, indent=2))
