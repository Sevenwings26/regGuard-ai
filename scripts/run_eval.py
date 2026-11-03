import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any, Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATA_DIR = os.path.join(REPO_ROOT, "data")
EVAL_DATASET_FILE = os.path.join(DATA_DIR, "eval_dataset.json")
README_FILE = os.path.join(REPO_ROOT, "README.md")
CLASSES = ["DRAFT_STR", "CLEAR_NO_SUSPICION", "ESCALATE_TO_OFFICER"]

def load_dataset(split: str) -> List[Dict[str, Any]]:
    if not os.path.exists(EVAL_DATASET_FILE):
        from scripts.generate_eval_dataset import generate_dataset
        generate_dataset()
    with open(EVAL_DATASET_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if split == "tuning":
        return [c for c in data if c.get("stratum") != "held_out"]
    if split == "heldout":
        return [c for c in data if c.get("stratum") == "held_out"]
    return data

def dataset_hash(cases: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()[:16]

def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown"

class EvalDB:
    """Isolated copy of regguard.db so eval never pollutes the demo database."""
    def __enter__(self):
        import app.manager as mgr
        import tools.sql_tool as sql_tool
        self._mgr, self._sql = mgr, sql_tool
        self._orig_mgr_db = None
        src = os.path.join(DATA_DIR, "regguard.db")
        self.tmp = os.path.join(DATA_DIR, "eval_regguard.db")
        if os.path.exists(src):
            shutil.copyfile(src, self.tmp)
        # Patch manager persistence to the temp DB by monkeypatching its db path resolution
        self._orig_persist = mgr.InvestigationManager.persist_custom_transaction_db
        tmp = self.tmp
        def patched(self_mgr, tx):
            # copy of original logic against tmp DB: simplest is temp swap of file path via env-free approach
            return _persist_to(tmp, tx)
        mgr.InvestigationManager.persist_custom_transaction_db = patched
        sql_tool._default_tool = sql_tool.SQLiteTool(db_path=self.tmp) if os.path.exists(self.tmp) else sql_tool._default_tool
        self._orig_sql_tool = sql_tool._default_tool
        return self
    def __exit__(self, *a):
        self._mgr.InvestigationManager.persist_custom_transaction_db = self._orig_persist
        import tools.sql_tool as sql_tool
        sql_tool._default_tool = None
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.tmp + suffix)
            except OSError:
                pass

def _persist_to(db_path: str, tx: Dict[str, Any]):
    import uuid
    from datetime import datetime, timezone
    account_id = tx.get("account_id") or "ACC-CUSTOM-01"
    cust_id = f"CUST-{account_id[-4:]}"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO customers (customer_id, full_name, entity_type, dob, bvn, nationality, risk_rating, kyc_status, created_at) VALUES (?, ?, ?, ?, ?, 'NGA', 'HIGH', 'VERIFIED', ?)",
                (cust_id, tx.get("customer_name", "Custom Customer"), tx.get("entity_type", "INDIVIDUAL"), tx.get("dob") or "1990-01-01", tx.get("bvn") or "22200011122", datetime.now(timezone.utc).isoformat()))
    cur.execute("INSERT OR IGNORE INTO accounts (account_id, customer_id, account_number, account_type, currency, balance, status, opened_date) VALUES (?, ?, ?, ?, 'NGN', ?, 'ACTIVE', '2022-01-01')",
                (account_id, cust_id, tx.get("account_number", "0998877665"), "SAVINGS" if tx.get("entity_type", "INDIVIDUAL") == "INDIVIDUAL" else "CORPORATE", float(tx.get("amount", 0)) * 1.5))
    cur.execute("INSERT OR REPLACE INTO transactions (transaction_id, account_id, transaction_type, amount, currency, narration, channel, timestamp, flag_code) VALUES (?, ?, ?, ?, 'NGN', ?, 'BRANCH_TELLER', ?, ?)",
                (tx.get("transaction_id") or f"TX-EVAL-{uuid.uuid4().hex[:6].upper()}", account_id, tx.get("transaction_type", "CASH_DEPOSIT"), float(tx.get("amount", 0)), tx.get("narration", ""), tx.get("timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), tx.get("flag_reason", "EVAL")))
    conn.commit(); conn.close()

# ---------------------------------------------------------------- baselines
def run_single_shot(case: Dict[str, Any], provider) -> Tuple[str, float]:
    """Real single-shot LLM call: transaction metadata only, no tools/graph/critique."""
    from pydantic import BaseModel
    from typing import Literal
    class SingleShot(BaseModel):
        disposition: Literal["DRAFT_STR", "CLEAR_NO_SUSPICION", "ESCALATE_TO_OFFICER"]
    tx = case["flagged_transaction"]
    prompt = (f"You are an AML compliance officer. Decide one disposition for this flagged transaction.\n"
              f"Customer: {tx.get('customer_name')}; Entity: {tx.get('entity_type')}; DOB: {tx.get('dob')}; "
              f"Amount: {tx.get('amount')} NGN; Type: {tx.get('transaction_type')}; Date: {tx.get('timestamp')}; "
              f"Flag: {tx.get('flag_reason')}; Narration: {tx.get('narration')}\n"
              f"Rules: individual cash limit N5,000,000 and corporate N10,000,000 (CBN 2022; pre-2022-11-01 corporate limit N10,000,000 under 2013 rules). "
              f"PEP name matches without corroborated identity are ambiguous.")
    t0 = time.perf_counter()
    try:
        out = provider.complete_structured(SingleShot, prompt)
        disp = out.disposition
    except Exception:
        # A provider that cannot answer the schema (e.g. deterministic mock) is not a
        # valid single-shot model baseline. Fail loudly instead of scoring a fallback.
        if provider.provider_name.startswith("mock/"):
            raise RuntimeError("Single-shot baseline requires a real LLM provider; use --provider live. The deterministic mock does not implement the SingleShot schema, and silently scoring its failure would fabricate a baseline.")
        try:
            text = provider.complete(prompt).upper()
            disp = next((c for c in CLASSES if c in text), "ESCALATE_TO_OFFICER")
        except Exception:
            disp = "ESCALATE_TO_OFFICER"
    return disp, round((time.perf_counter() - t0) * 1000, 2)

def _base_state(case, mode):
    tx = case["flagged_transaction"]
    _persist_to(os.path.join(DATA_DIR, "eval_regguard.db"), tx)
    return {"case_id": case["case_id"], "jurisdiction": "NGA_CBN", "flagged_transaction": tx, "claims": [],
            "unresolved_questions": [], "retry_count": 0, "max_retries": 1, "current_node": "START", "event_log": [],
            "last_event_sequence": 0, "evidence_sufficient": False, "final_status": "in_progress",
            "critique_decision": None, "audit_memo": None, "planned_queries": [], "mode": mode}

def run_rag_no_critique(case, mode) -> Tuple[str, List[Any], float, List[str]]:
    """Genuine ablation: plan -> act -> synthesize, skipping critique/refine.
    Disposition comes from synthesize's deterministic evidence derivation (no forced critique)."""
    from app.nodes.plan import plan_node
    from app.nodes.act import act_node, dispatch_tool
    from app.nodes.synthesize import synthesize_node
    t0 = time.perf_counter()
    state = _base_state(case, mode)
    ranked: List[str] = []
    # capture ranked regulation clause ids for Recall@k
    orig_search = None
    try:
        import tools.qdrant_hybrid as qh
        orig_search = qh.regulation_search
        def wrapped(query, effective_before=None, top_k=3):
            res = orig_search(query, effective_before, top_k)
            ranked.extend([c.get("clause_id") for c in res if c.get("clause_id")])
            return res
        import app.nodes.act as act_mod
        # act imports regulation_search by name; patch there
        act_mod.regulation_search = wrapped
    except Exception:
        pass
    try:
        state.update(plan_node(state))
        state.update(act_node(state))
        state["evidence_sufficient"] = True
        state["critique_decision"] = {"sufficient": True, "reason": "ablation: critique skipped", "missing": []}
        out = synthesize_node(state)
    finally:
        try:
            import app.nodes.act as act_mod
            from tools.qdrant_hybrid import regulation_search as rs
            act_mod.regulation_search = rs
        except Exception:
            pass
    claims = state.get("claims", [])
    return (out.get("audit_memo", {}) or {}).get("disposition", "ESCALATE_TO_OFFICER"), claims, round((time.perf_counter() - t0) * 1000, 2), ranked

def run_full(case, graph, mode) -> Tuple[str, List[Any], float, List[str]]:
    from tools.qdrant_hybrid import regulation_search as rs
    import app.nodes.act as act_mod
    ranked: List[str] = []
    orig = act_mod.regulation_search
    def wrapped(query, effective_before=None, top_k=3):
        res = orig(query, effective_before, top_k)
        ranked.extend([c.get("clause_id") for c in res if c.get("clause_id")])
        return res
    act_mod.regulation_search = wrapped
    t0 = time.perf_counter()
    try:
        state = _base_state(case, mode)
        init = dict(state)
        for step in graph.stream(init, stream_mode="updates"):
            for _n, upd in step.items():
                for k, v in upd.items():
                    state[k] = state.get(k, []) + v if k in ("claims", "unresolved_questions", "event_log") else v
    finally:
        act_mod.regulation_search = orig
    return (state.get("audit_memo", {}) or {}).get("disposition", "ESCALATE_TO_OFFICER"), state.get("claims", []), round((time.perf_counter() - t0) * 1000, 2), ranked

# ---------------------------------------------------------------- metrics
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z*z/n; c = p + z*z/(2*n); m = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (round((c-m)/d, 4), round((c+m)/d, 4))

def compute_metrics(records):
    matrix = {a: {p: 0 for p in CLASSES} for a in CLASSES}
    for r in records:
        if r["ground_truth"] in matrix and r["predicted"] in matrix[r["ground_truth"]]:
            matrix[r["ground_truth"]][r["predicted"]] += 1
    total = len(records); correct = sum(matrix[c][c] for c in CLASSES)
    per_class, f1s = {}, []
    for c in CLASSES:
        tp = matrix[c][c]; fp = sum(matrix[a][c] for a in CLASSES if a != c); fn = sum(matrix[c][p] for p in CLASSES if p != c)
        prec = tp/(tp+fp) if tp+fp else 1.0; rec = tp/(tp+fn) if tp+fn else 0.0; f1 = 2*prec*rec/(prec+rec) if prec+rec else 0.0
        per_class[c] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}
        f1s.append(f1)
    lat = sorted(r["latency_ms"] for r in records)
    def pct(p): return lat[min(len(lat)-1, int(len(lat)*p))] if lat else 0.0
    str_n = sum(matrix["DRAFT_STR"].values()); clear_n = sum(matrix["CLEAR_NO_SUSPICION"].values())
    pre2022 = [r for r in records if (r.get("tx_timestamp") or "")[:10] < "2022-11-01"]
    return {
        "total_cases": total, "accuracy": round(correct/total, 4) if total else 0.0,
        "accuracy_wilson95": wilson(correct, total), "macro_f1": round(sum(f1s)/len(f1s), 4),
        "majority_class_baseline": round(max(sum(matrix[c].values()) for c in CLASSES)/total, 4) if total else 0.0,
        "false_clear_rate_str_to_clear": round(matrix["DRAFT_STR"]["CLEAR_NO_SUSPICION"]/str_n, 4) if str_n else 0.0,
        "escalation_missed_to_clear_rate": round(matrix["ESCALATE_TO_OFFICER"]["CLEAR_NO_SUSPICION"]/sum(matrix["ESCALATE_TO_OFFICER"].values()), 4) if sum(matrix["ESCALATE_TO_OFFICER"].values()) else 0.0,
        "false_str_rate_clear_to_str": round(matrix["CLEAR_NO_SUSPICION"]["DRAFT_STR"]/clear_n, 4) if clear_n else 0.0,
        "str_recall": per_class["DRAFT_STR"]["recall"],
        "escalation_precision": per_class["ESCALATE_TO_OFFICER"]["precision"], "escalation_recall": per_class["ESCALATE_TO_OFFICER"]["recall"], "escalation_f1": per_class["ESCALATE_TO_OFFICER"]["f1"],
        "unsupported_claim_rate": round(sum(r.get("unsupported_claims", 0) for r in records)/max(1, sum(r.get("total_claims", 0) for r in records)), 4),
        "citation_resolved_rate": round(sum(r.get("resolved_citations", 0) for r in records)/max(1, sum(r.get("total_citations", 0) for r in records)), 4),
        "temporal_violation_rate_pre2022": round(sum(1 for r in pre2022 if r.get("temporal_violation"))/len(pre2022), 4) if pre2022 else 0.0,
        "pre2022_cases": len(pre2022),
        "clause_recall_at_2": round(sum(1 for r in records if r.get("expected_statute") and r["expected_statute"] in (r.get("ranked_clauses") or [])[:2])/max(1, sum(1 for r in records if r.get("expected_statute"))), 4),
        "clause_citation_rate": round(sum(1 for r in records if r.get("expected_statute") and r.get("retrieval_hit"))/max(1, sum(1 for r in records if r.get("expected_statute"))), 4),
        "p50_latency_ms": pct(0.50), "p95_latency_ms": pct(0.95),
        "confusion_matrix": matrix, "per_class": per_class,
        "per_stratum_accuracy": _per_stratum(records),
    }

def _per_stratum(records):
    out = {}
    for r in records:
        s = out.setdefault(r.get("stratum", "?"), [0, 0]); s[1] += 1; s[0] += int(r["ground_truth"] == r["predicted"])
    return {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0]/v[1], 4)} for k, v in sorted(out.items())}

def enrich(case, disp, claims, ranked):
    sources = [s for c in claims for s in (getattr(c, "supporting_sources", []) or [])]
    texts = " ".join(getattr(c, "text", "") for c in claims)
    known = set()
    try:
        known = {r["clause_id"] for r in json.load(open(os.path.join(DATA_DIR, "cbn_regulations.json")))}
    except Exception:
        pass
    resolved = sum(1 for s in sources if s in known)
    tx_ts = case["flagged_transaction"].get("timestamp", "")
    temporal = bool(tx_ts[:10] < "2022-11-01" and any("CBN-AML-2022" in s for s in sources) and not any("2013" in s or "2013" in texts for s in sources))
    return {"case_id": case["case_id"], "stratum": case.get("stratum"), "ground_truth": case["ground_truth_disposition"], "predicted": disp,
            "tx_timestamp": tx_ts, "expected_statute": case.get("expected_statute"),
            "unsupported_claims": sum(1 for c in claims if not getattr(c, "supporting_sources", None)),
            "total_claims": len(claims), "resolved_citations": resolved, "total_citations": len(sources),
            "temporal_violation": temporal, "retrieval_hit": bool(case.get("expected_statute") and case["expected_statute"] in " ".join(sources + [texts])),
            "ranked_clauses": ranked}

def run_evaluation(mode="fast", split="tuning", provider_kind="mock", update_readme=False, repeats=1):
    from app.graph import build_investigation_graph
    from core.llm_adapter import get_llm_provider, set_provider_override, MockLLMProvider, get_llm_usage_snapshot, reset_llm_usage
    cases = load_dataset(split)
    if mode == "fast":
        sampled, seen = [], {}
        for c in cases:
            seen.setdefault(c.get("stratum"), 0)
            if seen[c.get("stratum")] < 4:
                seen[c.get("stratum")] += 1; sampled.append(c)
        cases = sampled
    # provider selection: mock is renamed honestly, live uses the real configured provider
    if provider_kind == "live":
        set_provider_override(None)
        provider = get_llm_provider(mode="LIVE")
        graph_mode = "LIVE"
    else:
        provider = MockLLMProvider("mock/deterministic-offline")
        set_provider_override(provider)
        graph_mode = "MOCK"
    print(f"\nRegGuard eval | split={split} mode={mode} provider={provider.provider_name} cases={len(cases)}")
    reset_llm_usage()
    graph = build_investigation_graph()
    arms = {"single_shot": [], "rag_no_critique": [], "full_regguard": []}
    single_shot_valid = True
    with EvalDB():
        for case in cases:
            if single_shot_valid:
                try:
                    p, lat = run_single_shot(case, provider); r = enrich(case, p, [], []); r["latency_ms"] = lat; arms["single_shot"].append(r)
                except RuntimeError as e:
                    print(f"[SKIP] single-shot arm: {e}")
                    single_shot_valid = False
            p, claims, lat, ranked = run_rag_no_critique(case, graph_mode); r = enrich(case, p, claims, ranked); r["latency_ms"] = lat; arms["rag_no_critique"].append(r)
            p, claims, lat, ranked = run_full(case, graph, graph_mode); r = enrich(case, p, claims, ranked); r["latency_ms"] = lat; arms["full_regguard"].append(r)
    determinism = None
    if repeats and cases:
        disps = []
        with EvalDB():
            for _ in range(10):
                disps.append(run_full(cases[0], graph, graph_mode)[0])
        determinism = round(sum(1 for d in disps if d == disps[0]) / len(disps), 4)
    metrics = {k: compute_metrics(v) for k, v in arms.items() if v}
    if not single_shot_valid:
        metrics["single_shot"] = {"status": "not_run", "reason": "requires --provider live; deterministic mock cannot answer SingleShot schema"}
    usage = get_llm_usage_snapshot()
    payload = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "provider": provider.provider_name,
               "provider_kind": provider_kind, "split": split, "mode": mode, "dataset_size": len(cases),
               "dataset_hash": dataset_hash(cases), "git_sha": git_sha(), "ablations": metrics,
               "determinism_10x_first_case": determinism, "llm_usage": usage,
               "predictions": arms}
    out = os.path.join(DATA_DIR, f"eval_results_{provider_kind}_{split}_{mode}.json")
    with open(out, "w", encoding="utf-8") as f: json.dump(payload, f, indent=2, default=str)
    for k, m in metrics.items():
        if m.get("status") == "not_run":
            print(f"{k:<16} NOT RUN — {m['reason']}")
        else:
            print(f"{k:<16} acc={m['accuracy']*100:.1f}% macroF1={m['macro_f1']*100:.1f}% STR->CLEAR={m['false_clear_rate_str_to_clear']*100:.1f}% ESC->CLEAR={m['escalation_missed_to_clear_rate']*100:.1f}% CLEAR->STR={m['false_str_rate_clear_to_str']*100:.1f}% escF1={m['escalation_f1']*100:.1f}% recall@2={m['clause_recall_at_2']*100:.1f}% p50={m['p50_latency_ms']:.0f}ms")
    print(f"determinism(10x, provider={provider.provider_name})={determinism}  llm_usage={usage}")
    print(f"Saved: {out}")
    if update_readme:
        update_readme_tables(payload)
    set_provider_override(None)
    return payload

def fmt(m, k): return f"{m[k]*100:.1f}%"
def _row(label, m):
    if not m or m.get("status") == "not_run":
        return f"| {label} | not run (requires `--provider live`) | — | — | — | — | — | — | — |"
    return f"| {label} | {fmt(m,'accuracy')} ({m['accuracy_wilson95'][0]*100:.0f}–{m['accuracy_wilson95'][1]*100:.0f}) | {fmt(m,'macro_f1')} | {fmt(m,'false_clear_rate_str_to_clear')} | {fmt(m,'escalation_missed_to_clear_rate')} | {fmt(m,'false_str_rate_clear_to_str')} | {fmt(m,'escalation_f1')} | {fmt(m,'clause_recall_at_2')} | {m['p50_latency_ms']:.0f} ms |"
def update_readme_tables(payload):
    s, r, f = payload["ablations"].get("single_shot", {}), payload["ablations"]["rag_no_critique"], payload["ablations"]["full_regguard"]
    prov = payload["provider"]
    note = ("mock-provider simulation (deterministic offline provider, no LLM network calls — measures the graph/tools/guardrails, not model quality)" if payload["provider_kind"] == "mock" else f"LIVE provider `{prov}`")
    block = f"""### Evaluation results (auto-generated by `scripts/run_eval.py`)

> Provider: **{note}** | Split: `{payload['split']}` | Cases: {payload['dataset_size']} | Dataset hash: `{payload['dataset_hash']}` | Git: `{payload['git_sha']}` | Generated: {payload['timestamp']}
> Labeling rationale: an exact corroborated PEP/sanctions match is labeled `DRAFT_STR` as shorthand for "reportable high-risk match requiring STR/EDD filing review"; an uncorroborated name-only or DOB-mismatched match is labeled `ESCALATE_TO_OFFICER`. This is a synthetic benchmark labeling convention, not a claim that PEP status alone is an STR offence.

| System | Accuracy (95% CI) | Macro-F1 | STR→CLEAR | ESC→CLEAR (unsafe) | CLEAR→STR | Escalation F1 | Clause Recall@2 | p50 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{_row('(a) Single-shot LLM (no tools)', s)}
{_row('(b) LLM + tools/RAG (no critique/refine)', r)}
{_row('(c) Full RegGuard (critique/refine + guards)', f)}

Full RegGuard safety detail: unsupported-claim rate {fmt(f,'unsupported_claim_rate')}, citation-resolved rate {fmt(f,'citation_resolved_rate')}, temporal-violation rate on pre-2022 cases {fmt(f,'temporal_violation_rate_pre2022')} (n={f['pre2022_cases']}), expected-clause citation rate {fmt(f,'clause_citation_rate')}, determinism over 10 repeats {payload['determinism_10x_first_case']}, majority-class baseline {fmt(f,'majority_class_baseline')}. LLM usage during this run: {payload['llm_usage']}. Per-case predictions are stored in the `eval_results_*.json` artifact. Model-vs-model claims require two `--provider live` runs with different configured models; no such comparison is asserted here."""
    with open(README_FILE, encoding="utf-8") as fh: content = fh.read()
    start = content.find("## Empirical Benchmark & Ablation Evaluation")
    end = content.find("## Runbook & Verification")
    if start >= 0 and end > start:
        section = content[start:end]
        # replace only the auto-generated block if present, else replace whole benchmark section body up to Runbook
        marker = "### Evaluation results (auto-generated"
        if marker in section:
            pre = section[:section.find(marker)]
            content = content[:start] + pre + block + "\n\n---\n\n" + content[end:]
        else:
            header_end = section.find("\n", section.find("## Empirical"))
            content = content[:start] + section[:header_end+1] + "\n" + block + "\n\n---\n\n" + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as fh: fh.write(content)
        print("README benchmark tables updated from computed results.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="RegGuard honest evaluation harness")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--split", choices=["tuning", "heldout", "all"], default="tuning")
    ap.add_argument("--provider", choices=["mock", "live"], default="mock", help="mock=deterministic offline simulation; live=configured real provider (requires key/Ollama)")
    ap.add_argument("--update-readme", action="store_true")
    args = ap.parse_args()
    run_evaluation(mode=args.mode, split=args.split, provider_kind=args.provider, update_readme=args.update_readme)
