import os, sys
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path: sys.path.insert(0, REPO_ROOT)

from langgraph.graph import StateGraph, START, END
from app.state import InvestigationState, create_claim, verify_claims_chain

def node_1(s): return {"claims": [create_claim("C1", "Claim 1", ["S1"], "supported", "0"*64)]}
def node_2(s): return {"claims": [create_claim("C2", "Claim 2", ["S2"], "supported", s["claims"][-1].hash)]}
def node_3(s): return {"claims": [create_claim("C3", "Claim 3", ["S3"], "supported", s["claims"][-1].hash)]}

builder = StateGraph(InvestigationState)
builder.add_node("n1", node_1); builder.add_node("n2", node_2); builder.add_node("n3", node_3)
builder.add_edge(START, "n1"); builder.add_edge("n1", "n2"); builder.add_edge("n2", "n3"); builder.add_edge("n3", END)
graph = builder.compile()

final = graph.invoke({"case_id": "TEST", "claims": [], "unresolved_questions": [], "event_log": []})
claims = final["claims"]

assert len(claims) == 3, f"Expected 3 claims, got {len(claims)}"
assert [c.claim_id for c in claims] == ["C1", "C2", "C3"], "Claims out of insertion order"
assert claims[1].prev_hash == claims[0].hash and claims[2].prev_hash == claims[1].hash, "Hash chain link broken"
intact, broken_idx = verify_claims_chain(claims)
assert intact, f"Hash verification failed at {broken_idx}"
print("✓ Reducer check passed: 3 claims appended in order, zero overwrites, hash chain intact.")
