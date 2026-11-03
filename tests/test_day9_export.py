import asyncio
import os
import sys
import hashlib
import json
import pytest
from httpx import AsyncClient, ASGITransport

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app.server import app
from app.audit_memo import (
    generate_audit_memo_markdown,
    generate_audit_memo_html,
    get_canonical_json_for_claim
)
from app.state import compute_claim_hash

@pytest.fixture
def sample_snapshot_case_a():
    return {
        "investigation_id": "inv_test_case_a",
        "case_id": "CASE-A-STRUCTURING",
        "jurisdiction": "NGA_CBN",
        "final_status": "concluded",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0101",
            "customer_name": "Emeka Okafor",
            "account_id": "ACC-IND-9021",
            "amount": 5500000.0,
            "timestamp": "2023-01-02T11:45:00Z",
            "flag_reason": "RAPID_AGGREGATION_STRUCTURING"
        },
        "claims": [
            {
                "claim_id": "CLM-001",
                "text": "Customer conducted 3 cash transactions totaling N5,500,000.00 across 25.5 hours.",
                "supporting_sources": ["sqlite:transactions"],
                "status": "supported",
                "timestamp": "2023-01-02T12:00:00Z",
                "prev_hash": "0" * 64,
                "hash": compute_claim_hash({
                    "claim_id": "CLM-001",
                    "text": "Customer conducted 3 cash transactions totaling N5,500,000.00 across 25.5 hours.",
                    "supporting_sources": ["sqlite:transactions"],
                    "status": "supported",
                    "timestamp": "2023-01-02T12:00:00Z"
                }, "0" * 64)
            }
        ],
        "audit_memo": {
            "disposition": "DRAFT_STR",
            "subject_name": "Emeka Okafor",
            "account_id": "ACC-IND-9021",
            "summary": "Rapid aggregation structuring detected exceeding statutory N5,000,000.00 threshold.",
            "violations_found": ["CBN AML/CFT Regulations 2022 Section 10(3)"],
            "statutory_basis": "Mandatory STR filing required within 24 hours under Section 10(3).",
            "recommended_action": "Transmit formal STR to NFIU and freeze temporary debit privileges.",
            "ledger_tip_hash": "abc123"
        },
        "human_decision": {
            "decision": "APPROVE_STR",
            "notes": "Verified against transaction ledger. Transmit to NFIU immediately.",
            "officer_id": "OFFICER_CBN_99",
            "recorded_at": "2023-01-02T14:30:00Z"
        }
    }

@pytest.fixture
def sample_snapshot_case_b():
    return {
        "investigation_id": "inv_test_case_b",
        "case_id": "CASE-B-PEP-002",
        "jurisdiction": "NGA_CBN",
        "final_status": "escalated",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2023-0202",
            "customer_name": "Musa Ibrahim",
            "account_id": "ACC-IND-4412",
            "amount": 8200000.0,
            "timestamp": "2023-02-15T09:40:00Z",
            "flag_reason": "PEP_NAME_MATCH"
        },
        "claims": [
            {
                "claim_id": "CLM-001",
                "text": "PEP fuzzy match indicates 1.0 similarity to PEP watchlist entry 'Musa Ibrahim'.",
                "supporting_sources": ["watchlist:pep_database"],
                "status": "supported",
                "timestamp": "2023-02-15T10:00:00Z",
                "prev_hash": "0" * 64,
                "hash": "hash_clm_001"
            }
        ],
        "audit_memo": {
            "disposition": "ESCALATE_TO_OFFICER",
            "subject_name": "Musa Ibrahim",
            "account_id": "ACC-IND-4412",
            "summary": "Unresolvable identity discrepancy between PEP watchlist candidate and customer KYC.",
            "why_could_not_conclude": [
                "Customer DOB is 1985-04-12 whereas PEP entity DOB is 1952-11-03 (33-year discrepancy).",
                "High name similarity persists despite demographic divergence."
            ],
            "recommended_officer_action": "Conduct biometric BVN verification with NIBSS before clearing or reporting."
        }
    }

@pytest.fixture
def sample_snapshot_case_c():
    return {
        "investigation_id": "inv_test_case_c",
        "case_id": "CASE-C-TEMPORAL",
        "jurisdiction": "NGA_CBN",
        "final_status": "concluded",
        "flagged_transaction": {
            "transaction_id": "TX-NGA-2021-0303",
            "customer_name": "Kudirat Logistics Ltd",
            "account_id": "ACC-CORP-1011",
            "amount": 7500000.0,
            "timestamp": "2021-08-14T11:20:00Z",
            "flag_reason": "CORPORATE_CASH_THRESHOLD"
        },
        "claims": [],
        "audit_memo": {
            "disposition": "CLEAR_NO_SUSPICION",
            "subject_name": "Kudirat Logistics Ltd",
            "account_id": "ACC-CORP-1011",
            "summary": "Transaction conducted in 2021 governed by 2013 regulations; does not breach statutory N10M threshold.",
            "applicable_regulation": "CBN-AML-2013-SEC-02-1",
            "governing_limit": 10000000.0,
            "transaction_amount": 7500000.0,
            "cleared_reason": "Lawful commercial cash turnover compliant with applicable 2013 statutory limits."
        }
    }

def test_markdown_audit_memo_generation(sample_snapshot_case_a, sample_snapshot_case_b, sample_snapshot_case_c):
    """
    Day 9 Deliverable Verification:
    - Generates markdown compliance memo for Case A (STR), Case B (Escalation), and Case C (Clearance).
    - Asserts presence of required statutory headers, evidence ledger trail, and officer sign-off.
    """
    # 1. Case A (STR)
    md_a = generate_audit_memo_markdown(sample_snapshot_case_a)
    assert "# CENTRAL BANK OF NIGERIA (CBN) AML/CFT COMPLIANCE AUDIT MEMORANDUM" in md_a
    assert "AI Compliance Model:" in md_a
    assert "DRAFT_STR" in md_a
    assert "FORMAL SUSPICIOUS TRANSACTION REPORT (STR) DETAILS" in md_a
    assert "Nigerian Financial Intelligence Unit (NFIU)" in md_a
    assert "Emeka Okafor" in md_a
    assert "ACC-IND-9021" in md_a
    assert "OFFICER_CBN_99" in md_a
    assert "APPROVE_STR" in md_a
    assert "CLM-001" in md_a

    # 2. Case B (Escalation)
    md_b = generate_audit_memo_markdown(sample_snapshot_case_b)
    assert "ESCALATE_TO_OFFICER" in md_b
    assert "ESCALATION GAP ANALYSIS & WHY AGENT COULD NOT CONCLUDE" in md_b
    assert "Musa Ibrahim" in md_b
    assert "Customer DOB is 1985-04-12" in md_b
    assert "Biometric BVN verification" in md_b or "NIBSS" in md_b

    # 3. Case C (Clearance)
    md_c = generate_audit_memo_markdown(sample_snapshot_case_c)
    assert "CLEAR_NO_SUSPICION" in md_c
    assert "STATUTORY CLEARANCE ANALYSIS" in md_c
    assert "CBN-AML-2013-SEC-02-1" in md_c
    assert "10,000,000.00" in md_c
    assert "7,500,000.00" in md_c

def test_html_audit_memo_generation(sample_snapshot_case_a, sample_snapshot_case_b, sample_snapshot_case_c):
    """
    Day 9 Deliverable Verification:
    - Generates standalone, printable HTML compliance memo.
    - Asserts presence of official letterhead styling, responsive table, and print styles.
    """
    # 1. Case A HTML
    html_a = generate_audit_memo_html(sample_snapshot_case_a)
    assert "<!DOCTYPE html>" in html_a
    assert "Central Bank of Nigeria" in html_a
    assert "AI Compliance Model:" in html_a
    assert "Suspicious Transaction Report (STR)" in html_a
    assert "@media print" in html_a
    assert "Emeka Okafor" in html_a
    assert "CLM-001" in html_a
    assert "OFFICER_CBN_99" in html_a

    # 2. Case B HTML
    html_b = generate_audit_memo_html(sample_snapshot_case_b)
    assert "Senior Officer Escalation Dossier" in html_b
    assert "Reason Autonomous Action Halted" in html_b
    assert "Musa Ibrahim" in html_b

    # 3. Case C HTML
    html_c = generate_audit_memo_html(sample_snapshot_case_c)
    assert "Statutory Clearance Certificate" in html_c
    assert "CBN-AML-2013-SEC-02-1" in html_c

def test_canonical_json_and_sha256_integrity(sample_snapshot_case_a):
    """
    Verifies that get_canonical_json_for_claim produces deterministic JSON that
    matches compute_claim_hash byte-for-byte.
    """
    claim = sample_snapshot_case_a["claims"][0]
    canonical_str = get_canonical_json_for_claim(claim)
    
    # Recalculate hash over canonical JSON
    computed_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    
    assert computed_hash == claim["hash"]
    # Check that keys are alphabetically sorted
    data = json.loads(canonical_str)
    keys = list(data.keys())
    assert keys == sorted(keys)

@pytest.mark.asyncio
async def test_fastapi_audit_export_endpoints():
    """
    Day 9 API Endpoints Verification:
    - POST /investigations (runs Case A in CACHED mode)
    - GET /investigations/{id}/audit_memo
    - GET /investigations/{id}/export/markdown
    - GET /investigations/{id}/export/html
    - GET /investigations/{id}/claims/{claim_id}/verify
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start investigation
        start_res = await client.post(
            "/investigations",
            json={"case_id": "CASE-A-STRUCTURING", "mode": "CACHED"}
        )
        assert start_res.status_code == 200
        inv_id = start_res.json()["investigation_id"]

        # 2. Stream to completion
        async with client.stream("GET", f"/investigations/{inv_id}/stream") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if "investigation_completed" in line:
                    break

        # 3. Test GET /investigations/{id}/audit_memo
        memo_res = await client.get(f"/investigations/{inv_id}/audit_memo")
        assert memo_res.status_code == 200
        memo_data = memo_res.json()
        assert memo_data["investigation_id"] == inv_id
        assert memo_data["case_id"] == "CASE-A-STRUCTURING"
        assert memo_data["disposition"] == "DRAFT_STR"
        assert len(memo_data["markdown"]) > 0
        assert "<!DOCTYPE html>" in memo_data["html"]

        # 4. Test GET /investigations/{id}/export/markdown
        md_export = await client.get(f"/investigations/{inv_id}/export/markdown")
        assert md_export.status_code == 200
        assert "text/markdown" in md_export.headers["content-type"]
        assert f'attachment; filename="cbn_audit_memo_{inv_id}.md"' in md_export.headers["content-disposition"]
        assert "# CENTRAL BANK OF NIGERIA" in md_export.text

        # 5. Test GET /investigations/{id}/export/html
        html_export = await client.get(f"/investigations/{inv_id}/export/html")
        assert html_export.status_code == 200
        assert "text/html" in html_export.headers["content-type"]
        assert "<!DOCTYPE html>" in html_export.text
        assert "RegGuard Demo Bank Nigeria" in html_export.text

        # 6. Test GET /investigations/{id}/claims/{claim_id}/verify
        snapshot_res = await client.get(f"/investigations/{inv_id}")
        claims = snapshot_res.json().get("claims", [])
        assert len(claims) > 0
        target_claim = claims[0]

        verify_res = await client.get(f"/investigations/{inv_id}/claims/{target_claim['claim_id']}/verify")
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert verify_data["claim_id"] == target_claim["claim_id"]
        assert verify_data["is_valid"] is True
        assert verify_data["stored_hash"] == target_claim["hash"]
        assert verify_data["recalculated_hash"] == target_claim["hash"]

        # 7. Test 404 for invalid investigation ID
        not_found_res = await client.get("/investigations/inv_nonexistent_999/audit_memo")
        assert not_found_res.status_code == 404
